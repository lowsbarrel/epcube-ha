"""The rest of the API surface.

These groups cover routes that exist in the app but that no account here has
been able to exercise, so their response shapes are unknown and they return raw
JSON rather than models. They are exposed because a discovered route nobody can
call is not much use - and because `registry.py` lists another sixty beyond
these, reachable through `client.raw`.

Promote a route to a model the moment a real response is available.
"""

from __future__ import annotations

from typing import Any

from .base import EndpointGroup


class VppEndpoints(EndpointGroup):
    """`vpp/*` - virtual power plant enrolment and grid-services events.

    Untested: needs an account enrolled in a utility programme. `flip/updateSoc`
    in particular looks like remote state-of-charge control by an operator, so
    treat the write routes here with care.
    """

    async def user_info(self) -> Any:
        return await self._get("vpp/userInfo")

    async def programs(self) -> Any:
        return await self._get("vpp/allPrograms")

    async def site_programs(self, site_id: str | None = None) -> Any:
        return await self._get("vpp/site/programs", siteId=site_id)

    async def enrollments(self) -> Any:
        return await self._get("vpp/enrollments")

    async def enrollment_status(self) -> Any:
        return await self._get("vpp/globalEnrollmentStatus")

    async def events(self) -> Any:
        """Scheduled or past grid-services events."""
        return await self._get("vpp/events")

    async def global_soc(self) -> Any:
        """Operator-imposed state-of-charge target, if the site is enrolled."""
        return await self._get("vpp/flip/getGlobalSoc")


class SmartBreakerEndpoints(EndpointGroup):
    """`smartBreaker/*` - the companion smart breaker product.

    Untested: needs a breaker paired to the account. Note it has its own graph
    route, so per-circuit history is presumably available to those who have one.
    """

    async def graph(self, dev_id: str, **params: Any) -> Any:
        return await self._get("smartBreaker/queryDataGraph", devId=dev_id, **params)

    async def add(self, **body: Any) -> Any:
        return await self._post("smartBreaker/addDevice", body=body)

    async def update(self, **body: Any) -> Any:
        return await self._post("smartBreaker/updateDevice", body=body)

    async def save_settings(self, **body: Any) -> Any:
        return await self._post("smartBreaker/saveSettingData", body=body)


class MessageEndpoints(EndpointGroup):
    """`message/*` - the in-app notification inbox."""

    async def list(self, **params: Any) -> Any:
        return await self._get("message/messageList", **params)

    async def types(self) -> Any:
        return await self._get("message/messageTypeInfo")

    async def read_all(self) -> Any:
        return await self._post("message/readAll")

    async def set_push(self, enabled: bool) -> Any:
        return await self._post(
            "message/changeMsgPushStatus", body={"status": "1" if enabled else "0"}
        )


class SupportEndpoints(EndpointGroup):
    """`help/*`, `installLog/*`, `afterSale/*` - documentation and service."""

    async def help_list(self, **params: Any) -> Any:
        return await self._get("help/helpList", **params)

    async def help_detail(self, help_id: str) -> Any:
        return await self._get("help/helpDetail", id=help_id)

    async def install_log(self, **params: Any) -> Any:
        return await self._get("installLog/queryInstallLogInfo", **params)

    async def weather(self, **params: Any) -> Any:
        """`weatherApi/weather/getWeather` - the forecast the weather-aware
        charging mode is driven from."""
        return await self._get("weatherApi/weather/getWeather", **params)
