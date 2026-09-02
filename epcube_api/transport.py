"""HTTP plumbing: request shaping, error mapping and retries, over httpx.

A single async transport. Sync was dropped rather than duplicated - see
`endpoints/base.py` for the reasoning.

Error handling has to cover two layers, because the API reports failures in two
places. The EU cluster uses HTTP status codes; the US and JP clusters answer
HTTP 200 and put the real code in a `status` field inside the body. Anything
that only checks `response.status_code` silently treats an expired token on
those clusters as a successful empty response.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .const import (
    DEFAULT_BACKOFF,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    RATE_LIMIT_BACKOFF_MULTIPLIER,
    USER_AGENT,
    Region,
)
from .exceptions import (
    EpCubeAPIError,
    EpCubeAuthError,
    EpCubeConnectionError,
    EpCubeForbiddenError,
    EpCubeNotFoundError,
    EpCubeRateLimitError,
    EpCubeResponseError,
    EpCubeServerError,
    EpCubeTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


def normalize_token(token: str | None) -> str | None:
    """The header wants `Bearer <token>`; accept it with or without the prefix."""
    if not token:
        return None
    token = token.strip()
    return token if token.startswith("Bearer ") else f"Bearer {token}"


def redact(token: str | None) -> str:
    """Render a token for logs without disclosing it."""
    if not token:
        return "<none>"
    body = token.removeprefix("Bearer ")
    if len(body) <= 12:
        return "Bearer ***"
    return f"Bearer {body[:6]}…{body[-4:]} ({len(body)} chars)"


@dataclass(slots=True)
class Request:
    """One API call, independent of which transport executes it."""

    method: str
    path: str
    """Route without a leading slash, e.g. `device/homeDeviceInfo`."""
    params: dict[str, Any] | None = None
    json: dict[str, Any] | None = None
    auth: bool = True

    def with_params(self, **extra: Any) -> Request:
        merged = {**(self.params or {}), **extra}
        return Request(self.method, self.path, merged, self.json, self.auth)


@dataclass(slots=True)
class CallRecord:
    """One completed exchange, kept for diagnostics."""

    method: str
    path: str
    http_status: int | None
    api_status: int | None
    elapsed: float
    attempts: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class TransportConfig:
    region: Region = Region.EU
    token: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff: float = DEFAULT_BACKOFF
    language: str = DEFAULT_LANGUAGE
    user_agent: str = USER_AGENT
    history: list[CallRecord] = field(default_factory=list)
    history_limit: int = 200


class BaseTransport:
    """Request shaping, error mapping and retry policy, without the I/O."""

    def __init__(self, config: TransportConfig) -> None:
        self.config = config
        self.config.token = normalize_token(config.token)

    # -- identity --

    @property
    def region(self) -> Region:
        return self.config.region

    @property
    def base_url(self) -> str:
        return self.config.region.base_url

    @property
    def token(self) -> str | None:
        return self.config.token

    @token.setter
    def token(self, value: str | None) -> None:
        self.config.token = normalize_token(value)

    @property
    def history(self) -> list[CallRecord]:
        return self.config.history

    # -- request shaping --

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self, request: Request) -> dict[str, str]:
        headers = {
            "accept": "*/*",
            "accept-language": self.config.language,
            "user-agent": self.config.user_agent,
        }
        if request.json is not None:
            headers["content-type"] = "application/json"
        if request.auth:
            if not self.config.token:
                raise EpCubeAuthError(
                    "no token: call login(), or construct the client with token=",
                    path=request.path,
                )
            headers["authorization"] = self.config.token
        return headers

    @staticmethod
    def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
        """httpx rejects None values; the API wants them absent anyway."""
        if not params:
            return None
        return {k: v for k, v in params.items() if v is not None}

    # -- response handling --

    def _process(self, response: httpx.Response, request: Request) -> tuple[Any, int | None]:
        """Return `(data, api_status)` or raise the mapped error."""
        http_status = response.status_code
        path = request.path

        if http_status >= 400:
            raise self._map_status(http_status, path, response.text[:300], http_status=http_status)

        try:
            envelope = response.json()
        except ValueError:
            raise EpCubeResponseError(
                f"expected JSON, got {response.headers.get('content-type')!r}: "
                f"{response.text[:200]}",
                path=path,
            ) from None

        if not isinstance(envelope, dict):
            # A few routes return a bare list at the top level.
            return envelope, None

        api_status = envelope.get("status")
        if api_status is not None:
            try:
                api_status = int(api_status)
            except (TypeError, ValueError):
                api_status = None

        if api_status is not None and api_status != 200:
            message = envelope.get("message") or "request rejected"
            raise self._map_status(
                api_status, path, message, http_status=http_status, api_status=api_status
            )

        return envelope.get("data"), api_status

    @staticmethod
    def _map_status(
        code: int,
        path: str,
        message: str,
        *,
        http_status: int | None = None,
        api_status: int | None = None,
    ) -> EpCubeAPIError:
        kwargs = {
            "http_status": http_status,
            "api_status": api_status,
            "path": path,
        }
        if code == 401:
            return EpCubeAuthError(
                f"token rejected: {message}. A token issued for a different region "
                f"fails exactly like an expired one - check the region first",
                **kwargs,
            )
        if code == 403:
            return EpCubeForbiddenError(f"access denied: {message}", **kwargs)
        if code == 404:
            return EpCubeNotFoundError(f"no such route: {message}", **kwargs)
        if code == 429:
            return EpCubeRateLimitError(f"rate limited: {message}", **kwargs)
        if code >= 500:
            return EpCubeServerError(
                f"server error: {message}. Several routes answer a malformed "
                f"request this way rather than with a validation error",
                **kwargs,
            )
        return EpCubeAPIError(f"request failed: {message}", **kwargs)

    # -- retry policy --

    def _retry_delay(self, attempt: int, error: Exception) -> float | None:
        """Seconds to wait before the next attempt, or None to give up."""
        if attempt >= self.config.max_retries:
            return None
        if isinstance(error, EpCubeRateLimitError):
            return self.config.backoff * RATE_LIMIT_BACKOFF_MULTIPLIER * attempt
        if isinstance(error, (EpCubeServerError, EpCubeConnectionError)):
            return self.config.backoff * attempt
        return None

    def _record(self, record: CallRecord) -> None:
        history = self.config.history
        history.append(record)
        if len(history) > self.config.history_limit:
            del history[: len(history) - self.config.history_limit]

    @staticmethod
    def _wrap_transport_error(exc: Exception, path: str) -> EpCubeConnectionError:
        if isinstance(exc, httpx.TimeoutException):
            return EpCubeTimeoutError(f"{path}: timed out")
        return EpCubeConnectionError(f"{path}: {exc}")

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.config.timeout, connect=self.config.connect_timeout)


class AsyncTransport(BaseTransport):
    """Async transport. Owns its httpx client unless one is supplied."""

    def __init__(
        self,
        config: TransportConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self._client = client
        self._owns_client = client is None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout())
        return self._client

    async def request(self, request: Request) -> Any:
        started = time.perf_counter()
        attempt = 0
        last_error: Exception | None = None
        http_status: int | None = None
        api_status: int | None = None

        while True:
            attempt += 1
            try:
                response = await self.client.request(
                    request.method,
                    self._url(request.path),
                    params=self._clean_params(request.params),
                    json=request.json,
                    headers=self._headers(request),
                    timeout=self._timeout(),
                )
                http_status = response.status_code
                data, api_status = self._process(response, request)
            except (httpx.TransportError, httpx.HTTPError) as exc:
                last_error = self._wrap_transport_error(exc, request.path)
            except EpCubeAPIError as exc:
                last_error = exc
                http_status = exc.http_status
                api_status = exc.api_status
            except EpCubeResponseError as exc:
                last_error = exc
            else:
                self._record(
                    CallRecord(
                        request.method,
                        request.path,
                        http_status,
                        api_status,
                        time.perf_counter() - started,
                        attempt,
                    )
                )
                return data

            delay = self._retry_delay(attempt, last_error)
            if delay is None:
                self._record(
                    CallRecord(
                        request.method,
                        request.path,
                        http_status,
                        api_status,
                        time.perf_counter() - started,
                        attempt,
                        str(last_error),
                    )
                )
                raise last_error
            _LOGGER.debug(
                "retrying %s in %.1fs (attempt %d/%d): %s",
                request.path,
                delay,
                attempt,
                self.config.max_retries,
                last_error,
            )
            await asyncio.sleep(delay)

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
