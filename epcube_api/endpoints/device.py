"""Device state, telemetry and control - the `device/*` routes."""

from __future__ import annotations

from datetime import date
from typing import Any

from ..const import WorkMode
from ..models import (
    DeviceDetail,
    DeviceSummary,
    LiveSnapshot,
    ModeConfig,
    NetworkInfo,
    OutageEvent,
    PvStrings,
    SwitchModeRequest,
    Warranty,
)
from .base import EndpointGroup, parse_list, parse_model


class DeviceEndpoints(EndpointGroup):
    """Everything about a single device.

    Most routes here are keyed on the numeric `dev_id`, which only
    `home_info()` reports - so a fresh session usually starts there.
    """

    # -- reads --

    async def home_info(self, sn: str, day: date | None = None) -> LiveSnapshot:
        """Live snapshot for a plant serial. The app's home screen.

        The `dayMonthYearFormat` parameter scopes the day-total fields; it does
        not turn this into a historical query.
        """
        return await self._get(
            "device/homeDeviceInfo",
            parse_model(LiveSnapshot),
            sgSn=sn,
            dayMonthYearFormat=(day or date.today()).strftime("%Y-%m-%d"),
        )

    async def all(self) -> list[DeviceSummary]:
        """Every device on the account, with the richest metadata the API has."""
        return await self._get("device/deviceList", parse_list(DeviceSummary))

    async def detail(self, dev_id: str) -> DeviceDetail:
        """Model, battery capacity, activation and warranty dates."""
        return await self._get("device/userDeviceInfo", parse_model(DeviceDetail), devId=dev_id)

    async def mode(self, dev_id: str) -> ModeConfig:
        """Current mode, reserve levels and the full tariff calendar.

        The read side of `switch_mode`, and the input `SwitchModeRequest`
        requires to build a write that preserves everything it isn't changing.
        """
        return await self._get("device/getSwitchMode", parse_model(ModeConfig), devId=dev_id)

    async def pv_strings(self, dev_id: str) -> PvStrings:
        """Per-MPPT-string voltage, current and power.

        The only route exposing individual strings, which makes it the only way
        to see one underperforming from the cloud side.
        """
        return await self._get("device/getSolarPvPower", PvStrings.from_api, devId=dev_id)

    async def outages(self, dev_id: str) -> list[OutageEvent]:
        """Grid outage log, with start, end and duration for each event."""
        return await self._get("device/getDevPowerCutLog", parse_list(OutageEvent), devId=dev_id)

    async def network(self, dev_id: str) -> NetworkInfo:
        """Wi-Fi name, signal level and connection state."""
        return await self._get("device/netWorkInfo", parse_model(NetworkInfo), devId=dev_id)

    async def warranty(self, dev_id: str) -> Warranty:
        """Activation and warranty-end dates."""
        return await self._get("device/getWarranty", parse_model(Warranty), devId=dev_id)

    async def firmware_version(self, dev_id: str) -> Any:
        """Raw `device/getDevPcsVersion`. Shape not yet modelled."""
        return await self._get("device/getDevPcsVersion", devId=dev_id)

    async def check_upgrade(self, dev_id: str) -> Any:
        """Whether a firmware update is available. Raw shape."""
        return await self._get("device/checkUpgrade", devId=dev_id)

    # -- writes --

    async def switch_mode(self, request: SwitchModeRequest) -> Any:
        """Apply a complete configuration.

        Takes a `SwitchModeRequest` rather than a dict on purpose: the endpoint
        resets every field the payload omits, so a partial body silently wipes
        the tariff calendar and the reserve levels. Build the request with
        `SwitchModeRequest.from_config(await client.device.mode(dev_id))` and
        change only what you mean to.
        """
        return await self._post("device/switchMode", body=request.api_dump())

    async def set_mode(
        self,
        config: ModeConfig,
        mode: WorkMode | int,
        *,
        dev_id: str | None = None,
    ) -> Any:
        """Change the operating mode, preserving everything else.

        `config` must be a fresh read from `mode()` - it is the source of the
        values that get echoed back untouched.
        """
        request = SwitchModeRequest.from_config(config, dev_id=dev_id, work_status=mode)
        return await self.switch_mode(request)

    async def set_reserve_soc(
        self,
        config: ModeConfig,
        *,
        self_consumption: int | None = None,
        backup: int | None = None,
        dev_id: str | None = None,
    ) -> Any:
        """Adjust reserve levels without touching the operating mode.

        Uses `onlySave`, so the device keeps running in whatever mode it is in.
        """
        request = SwitchModeRequest.from_config(config, dev_id=dev_id, only_save=True)
        changes: dict[str, Any] = {}
        if self_consumption is not None:
            changes["self_consumption_reserve_soc"] = str(self_consumption)
        if backup is not None:
            changes["backup_power_reserve_soc"] = str(backup)
        if not changes:
            raise ValueError("nothing to change: pass self_consumption and/or backup")
        return await self.switch_mode(request.with_changes(**changes))

    async def set_grid_charging(
        self,
        config: ModeConfig,
        allowed: bool,
        *,
        dev_id: str | None = None,
    ) -> Any:
        """Allow or forbid charging the battery from the grid."""
        request = SwitchModeRequest.from_config(config, dev_id=dev_id, only_save=True)
        return await self.switch_mode(
            request.with_changes(allow_charging_from_grid="1" if allowed else "0")
        )
