from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import TracebackType
from typing import Any, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .const import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_ATTEMPTS,
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
    TransportConfig,
    redact,
)


def _plant_today(live: LiveSnapshot) -> date:
    # Host TZ can be a day behind a UTC+ plant near local midnight.
    try:
        zone = ZoneInfo(live.from_timezone) if live.from_timezone else None
    except ZoneInfoNotFoundError, ValueError:
        zone = None
    return datetime.now(zone).date()


class RawEndpoints(EndpointGroup):
    async def get(self, path: str, **params: Any) -> Any:
        return await self._get(path, **params)

    async def post(self, path: str, body: dict[str, Any] | None = None, **params: Any) -> Any:
        return await self._post(path, body, **params)


class EpCubeAsyncClient:
    _transport: AsyncTransport

    def __init__(
        self,
        region: Region | str = Region.EU,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        language: str = DEFAULT_LANGUAGE,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._transport = AsyncTransport(
            self._config(region, token, timeout, connect_timeout, max_attempts, language),
            http_client,
        )
        self.account = AccountEndpoints(self._transport)
        self.device = DeviceEndpoints(self._transport)
        self.data = DataEndpoints(self._transport)
        self.public = PublicEndpoints(self._transport)
        self.vpp = VppEndpoints(self._transport)
        self.breaker = SmartBreakerEndpoints(self._transport)
        self.messages = MessageEndpoints(self._transport)
        self.support = SupportEndpoints(self._transport)
        self.raw = RawEndpoints(self._transport)

    @staticmethod
    def _config(
        region: Region | str,
        token: str | None,
        timeout: float,
        connect_timeout: float,
        max_attempts: int,
        language: str,
    ) -> TransportConfig:
        return TransportConfig(
            region=Region.parse(region),
            token=token,
            timeout=timeout,
            connect_timeout=connect_timeout,
            max_attempts=max_attempts,
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
        return self._transport.history

    def __repr__(self) -> str:
        return f"{type(self).__name__}(region={self.region.value}, token={redact(self.token)})"

    async def login(self, username: str, password: str, *, attempts: int = 5) -> str:
        from .auth import async_login

        token = await async_login(self, username, password, attempts=attempts)
        self.token = token
        return token

    async def resolve_device(self, sn: str | None = None) -> tuple[str, str, LiveSnapshot]:
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
        include_config: bool = True,
        include_totals: bool = True,
        include_series: bool = True,
        include_outages: bool = False,
    ) -> Snapshot:
        _, dev_id, live = await self.resolve_device(sn)
        today = _plant_today(live)

        sections: dict[str, Any] = {
            "mode": self.device.mode(dev_id),
            "pv": self.device.pv_strings(dev_id),
        }
        if include_config:
            sections["detail"] = self.device.detail(dev_id)
            sections["network"] = self.device.network(dev_id)
            sections["summary"] = self.device.all()
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
        if "summary" in values:
            values["summary"] = next((d for d in values["summary"] if d.id == dev_id), None)

        return Snapshot(dev_id=dev_id, live=live, errors=errors, **values)

    async def probe(self, path: str, **params: Any) -> tuple[bool, Any]:
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
