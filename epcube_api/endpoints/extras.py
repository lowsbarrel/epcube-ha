from __future__ import annotations

from typing import Any

from .base import EndpointGroup


class VppEndpoints(EndpointGroup):
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
        return await self._get("vpp/events")

    async def global_soc(self) -> Any:
        return await self._get("vpp/flip/getGlobalSoc")


class SmartBreakerEndpoints(EndpointGroup):
    async def graph(self, dev_id: str, **params: Any) -> Any:
        return await self._get("smartBreaker/queryDataGraph", devId=dev_id, **params)

    async def add(self, **body: Any) -> Any:
        return await self._post("smartBreaker/addDevice", body=body)

    async def update(self, **body: Any) -> Any:
        return await self._post("smartBreaker/updateDevice", body=body)

    async def save_settings(self, **body: Any) -> Any:
        return await self._post("smartBreaker/saveSettingData", body=body)


class MessageEndpoints(EndpointGroup):
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
    async def help_list(self, **params: Any) -> Any:
        return await self._get("help/helpList", **params)

    async def help_detail(self, help_id: str) -> Any:
        return await self._get("help/helpDetail", id=help_id)

    async def install_log(self, **params: Any) -> Any:
        return await self._get("installLog/queryInstallLogInfo", **params)

    async def weather(self, **params: Any) -> Any:
        return await self._get("weatherApi/weather/getWeather", **params)
