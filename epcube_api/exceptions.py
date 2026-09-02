"""Exception hierarchy.

Everything raised by this package derives from `EpCubeError`, so a caller that
only wants "did it work" can catch that one type. The subclasses exist because
the sensible reaction differs: a token error needs a new token, a rate limit
needs patience, and a payload error needs a code change.
"""

from __future__ import annotations

from typing import Any


class EpCubeError(Exception):
    """Base class for every failure this package raises."""


class EpCubeConnectionError(EpCubeError):
    """The request never produced a response: DNS, TCP, TLS or timeout."""


class EpCubeTimeoutError(EpCubeConnectionError):
    """The request exceeded its timeout budget, including all retries."""


class EpCubeAPIError(EpCubeError):
    """The server answered, but with a failure.

    Carries both layers, because the API reports errors in two different places:
    the HTTP status, and a `status` field inside an otherwise-200 body.
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        api_status: int | None = None,
        path: str | None = None,
        payload: Any = None,
    ) -> None:
        self.http_status = http_status
        self.api_status = api_status
        self.path = path
        self.payload = payload
        detail = []
        if path:
            detail.append(path)
        if http_status is not None:
            detail.append(f"HTTP {http_status}")
        if api_status is not None and api_status != http_status:
            detail.append(f"API status {api_status}")
        suffix = f" ({', '.join(detail)})" if detail else ""
        super().__init__(f"{message}{suffix}")


class EpCubeAuthError(EpCubeAPIError):
    """Missing, invalid or expired token.

    The US and JP clusters return this as HTTP 200 with `status: 401` in the
    body, and a token issued for a different region looks identical to an
    expired one -- check the region before assuming the token is stale.
    """


class EpCubeForbiddenError(EpCubeAuthError):
    """Authenticated, but not allowed to touch this device or endpoint."""


class EpCubeRateLimitError(EpCubeAPIError):
    """HTTP 429. Retried automatically; raised once the retries run out."""


class EpCubeServerError(EpCubeAPIError):
    """5xx, or a body status of 500. Often means the parameters were wrong:
    several endpoints answer a malformed request with a server exception rather
    than a validation error."""


class EpCubeNotFoundError(EpCubeAPIError):
    """HTTP 404. The route does not exist on this cluster."""


class EpCubeResponseError(EpCubeError):
    """The response arrived but could not be understood: not JSON, or shaped
    differently from what the model expects."""

    def __init__(self, message: str, *, path: str | None = None, payload: Any = None) -> None:
        self.path = path
        self.payload = payload
        super().__init__(f"{path}: {message}" if path else message)


class EpCubeCaptchaError(EpCubeError):
    """The login slide-puzzle was not solved.

    The offset is found by template matching, which does not always land on the
    first try; the login helper retries before giving up, so seeing this means
    several attempts in a row failed.
    """


class EpCubeLoginError(EpCubeError):
    """Credentials rejected by the login endpoint."""
