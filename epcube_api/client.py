"""`EpCubeAsyncClient` - the client.

Async-only by design; see `endpoints/base.py` for why. The namespaces:

    client.account   user/* and the signed-in user
    client.device    device state, telemetry and control
    client.data      energy totals and time series
    client.public    open/* (no token needed)
    client.vpp       virtual power plant (untested)
    client.breaker   smart breaker (untested)
    client.messages  notification inbox
    client.support   help, install logs, weather
    client.raw       any route by name, for the ones not modelled yet
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import TracebackType
from typing import Any, Self

import httpx

from .const import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    Region,
    Scope,
)
from .endpoints import (
    AccountEndpoints,
    DataEndpoints,
    DeviceEndpoints,
    MessageEndpoints,
    PublicEndpoints,
    SmartBreakerEndpoints,
    SupportEndpoints,
    VppEndpoints,
)
from .endpoints.base import EndpointGroup
from .exceptions import EpCubeAPIError, EpCubeError
from .models import LiveSnapshot
from .models.snapshot import Snapshot
from .transport import (
    AsyncTransport,
    CallRecord,
    Request,
    TransportConfig,
    redact,
)


class RawEndpoints(EndpointGroup):
    """Escape hatch for routes without a typed wrapper.

    `docs/api-endpoints.md` lists every route found in the app; most are not
    modelled because no response has been observed. Use this to explore one, then
    promote it to a real endpoint once its shape is known.
    """

    async def get(self, path: str, **params: Any) -> Any:
        return await self._call(Request("GET", path, params=params or None))

    async def post(self, path: str, body: dict[str, Any] | None = None, **params: Any) -> Any:
        return await self._call(Request("POST", path, params=params or None, json=body))


class _ClientBase:
    """Shared construction, identity and diagnostics."""

    _transport: AsyncTransport

    def _bind(self, transport: AsyncTransport) -> None:
        self._transport = transport
        self.account = AccountEndpoints(transport)
        self.device = DeviceEndpoints(transport)
        self.data = DataEndpoints(transport)
        self.public = PublicEndpoints(transport)
        self.vpp = VppEndpoints(transport)
        self.breaker = SmartBreakerEndpoints(transport)
        self.messages = MessageEndpoints(transport)
        self.support = SupportEndpoints(transport)
        self.raw = RawEndpoints(transport)

    @staticmethod
    def _config(
        region: Region | str,
        token: str | None,
        timeout: float,
        connect_timeout: float,
        max_retries: int,
        language: str,
    ) -> TransportConfig:
        return TransportConfig(
            region=Region.parse(region),
            token=token,
            timeout=timeout,
            connect_timeout=connect_timeout,
            max_retries=max_retries,
            language=language,
        )

    @property
    def region(self) -> Region:
        return self._transport.region

    @property
    def base_url(self) -> str:
        return self._transport.base_url

    @property
    def token(self) -> str | None:
        return self._transport.token

    @token.setter
    def token(self, value: str | None) -> None:
        self._transport.token = value

    @property
    def calls(self) -> list[CallRecord]:
        """Every exchange this client has made, newest last."""
        return self._transport.history

    def __repr__(self) -> str:
        return f"{type(self).__name__}(region={self.region.value}, token={redact(self.token)})"


class EpCubeAsyncClient(_ClientBase):
    """Async client. The one to use inside an event loop.

    ```python
    async with EpCubeAsyncClient(region="EU", token=token) as client:
        account = await client.account.base()
        snap = await client.snapshot(account.def_dev_sg_sn)
        print(snap.summary_line())
    ```
    """

    def __init__(
        self,
        region: Region | str = Region.EU,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        language: str = DEFAULT_LANGUAGE,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        config = self._config(region, token, timeout, connect_timeout, max_retries, language)
        self._bind(AsyncTransport(config, http_client))

    async def login(self, username: str, password: str, *, attempts: int = 5) -> str:
        """Sign in and store the resulting token on this client."""
        from .auth import async_login

        token = await async_login(self, username, password, attempts=attempts)
        self.token = token
        return token

    async def resolve_device(self, sn: str | None = None) -> tuple[str, str, LiveSnapshot]:
        """Work out `(sn, dev_id, live)` from whatever is known.

        The plant serial comes from the account when not supplied, and the
        numeric device id only ever comes from the live snapshot.
        """
        if sn is None:
            account = await self.account.base()
            sn = account.def_dev_sg_sn
            if not sn:
                raise EpCubeError("account reports no default plant serial; pass sn=")
        live = await self.device.home_info(sn)
        if not live.dev_id:
            raise EpCubeError("homeDeviceInfo returned no devId")
        return sn, live.dev_id, live

    async def snapshot(
        self,
        sn: str | None = None,
        *,
        include_totals: bool = True,
        include_series: bool = True,
        include_outages: bool = False,
    ) -> Snapshot:
        """Gather live state and its supporting reads concurrently.

        Only the live read is allowed to fail the call; everything else records
        its error and leaves its section empty.
        """
        _, dev_id, live = await self.resolve_device(sn)
        today = date.today()

        sections: dict[str, Any] = {
            "mode": self.device.mode(dev_id),
            "detail": self.device.detail(dev_id),
            "pv": self.device.pv_strings(dev_id),
            "network": self.device.network(dev_id),
        }
        if include_outages:
            sections["outages"] = self.device.outages(dev_id)
        if include_series:
            sections["series"] = self.data.series(dev_id, Scope.DAY, today)
        if include_totals:
            sections["today"] = self.data.totals(dev_id, Scope.DAY, today)
            sections["month"] = self.data.totals(dev_id, Scope.MONTH, today)
            sections["year"] = self.data.totals(dev_id, Scope.YEAR, today)
            sections["lifetime"] = self.data.totals(dev_id, Scope.LIFETIME, today)

        names = list(sections)
        results = await asyncio.gather(*sections.values(), return_exceptions=True)

        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException):
                errors[name] = str(result)
            else:
                values[name] = result

        # deviceList is a whole-account read; match it to this device.
        try:
            devices = await self.device.all()
            values["summary"] = next((d for d in devices if str(d.id) == str(dev_id)), None)
        except EpCubeError as exc:
            errors["summary"] = str(exc)

        return Snapshot(dev_id=dev_id, live=live, errors=errors, **values)

    async def probe(self, path: str, **params: Any) -> tuple[bool, Any]:
        """Try an unmodelled route. Returns `(ok, payload_or_error_message)`.

        Handy for working through `docs/api-endpoints.md`: many routes answer a
        wrong parameter set with a 500 rather than a validation error, so the
        distinction between "absent" and "called wrongly" is the 404.
        """
        try:
            return True, await self.raw.get(path, **params)
        except EpCubeAPIError as exc:
            return False, str(exc)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
