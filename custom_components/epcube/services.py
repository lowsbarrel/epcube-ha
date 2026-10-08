from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from epcube_api import ModeConfig, TouWindow, WorkMode

from .const import DOMAIN
from .coordinator import EpCubeCoordinator
from .override import CHARGE, DISCHARGE, HOLD

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TOU_SCHEDULE = "set_tou_schedule"
SERVICE_SET_OPERATING_MODE = "set_operating_mode"
SERVICE_FORCE_CHARGE = "force_charge"
SERVICE_FORCE_DISCHARGE = "force_discharge"
SERVICE_HOLD_BATTERY = "hold_battery"
SERVICE_CLEAR_OVERRIDE = "clear_override"

ATTR_DEVICE_ID = "device_id"
ATTR_TARGET_SOC = "target_soc"
ATTR_DURATION = "duration"
ATTR_MODE = "mode"
ATTR_RESERVE_SOC = "reserve_soc"
ATTR_APPLY = "apply"

MODES = {
    "self_consumption": WorkMode.SELF_CONSUMPTION,
    "time_of_use": WorkMode.TIME_OF_USE,
    "backup": WorkMode.BACKUP,
}

WINDOW_KEYS = (
    "peak",
    "mid_peak",
    "off_peak",
    "peak_non_workday",
    "mid_peak_non_workday",
    "off_peak_non_workday",
)

_TARGET = {vol.Required(ATTR_DEVICE_ID): cv.string}

SOC = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))

DURATION = vol.All(cv.time_period, vol.Range(min=timedelta(minutes=1)))

SCHEMA_TOU = vol.Schema(
    {
        **_TARGET,
        **{vol.Optional(key): vol.Any(None, cv.ensure_list) for key in WINDOW_KEYS},
        vol.Optional(ATTR_APPLY, default=False): cv.boolean,
    }
)

SCHEMA_MODE = vol.Schema(
    {**_TARGET, vol.Required(ATTR_MODE): vol.In(MODES), vol.Optional(ATTR_RESERVE_SOC): SOC}
)

SCHEMA_CHARGE = vol.Schema(
    {**_TARGET, vol.Required(ATTR_TARGET_SOC): SOC, vol.Optional(ATTR_DURATION): DURATION}
)

SCHEMA_DISCHARGE = vol.Schema(
    {**_TARGET, vol.Required(ATTR_TARGET_SOC): SOC, vol.Optional(ATTR_DURATION): DURATION}
)

SCHEMA_HOLD = vol.Schema({**_TARGET, vol.Optional(ATTR_DURATION): DURATION})

SCHEMA_CLEAR = vol.Schema(_TARGET)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> EpCubeCoordinator:
    device_id = call.data[ATTR_DEVICE_ID]
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": device_id},
        )

    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data

    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="device_not_loaded",
        translation_placeholders={"device_id": device_id},
    )


def _windows(call: ServiceCall, key: str) -> list[str] | None:
    raw = call.data.get(key)
    if raw is None:
        return None

    windows: list[str] = []
    for item in raw:
        text: str | None
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict) and "start" in item and "end" in item:
            price = item.get("price")
            try:
                text = TouWindow(
                    start=str(item["start"]),
                    end=str(item["end"]),
                    price=float(price) if price is not None else None,
                ).to_api()
            except TypeError, ValueError:
                text = None
        else:
            text = None

        if text is None or TouWindow.parse(text) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="bad_tou_window",
                translation_placeholders={"window": str(item), "field": key},
            )
        windows.append(text)
    return windows


def _duration(call: ServiceCall) -> timedelta | None:
    return call.data.get(ATTR_DURATION)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CLEAR_OVERRIDE):
        return

    async def set_tou_schedule(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        windows: dict[str, Any] = {key: _windows(call, key) for key in WINDOW_KEYS}
        apply = call.data[ATTR_APPLY]
        device = coordinator.client.device
        await coordinator.async_write(
            lambda config: device.set_tou_schedule(config, apply=apply, **windows)
        )

    async def set_operating_mode(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        mode = MODES[call.data[ATTR_MODE]]
        reserve = call.data.get(ATTR_RESERVE_SOC)
        device = coordinator.client.device

        async def write(config: ModeConfig) -> None:
            if mode is WorkMode.TIME_OF_USE and not config.has_tou_schedule:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="no_tou_schedule"
                )
            if reserve is not None:
                # Reserve first, so the mode change lands on the intended floor.
                field = "backup" if mode is WorkMode.BACKUP else "self_consumption"
                await device.set_reserve_soc(config, **{field: reserve})
                # set_mode carries the reserve, so rebuild it from the updated state.
                config = await device.mode(coordinator.device_id)
            await device.set_mode(config, mode)

        await coordinator.async_write(write)

    async def force_charge(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        await coordinator.overrides.async_start(
            CHARGE, target_soc=call.data[ATTR_TARGET_SOC], duration=_duration(call)
        )

    async def force_discharge(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        await coordinator.overrides.async_start(
            DISCHARGE, target_soc=call.data[ATTR_TARGET_SOC], duration=_duration(call)
        )

    async def hold_battery(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        await coordinator.overrides.async_start(HOLD, duration=_duration(call))

    async def clear_override(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        await coordinator.overrides.async_clear()

    for name, handler, schema in (
        (SERVICE_SET_TOU_SCHEDULE, set_tou_schedule, SCHEMA_TOU),
        (SERVICE_SET_OPERATING_MODE, set_operating_mode, SCHEMA_MODE),
        (SERVICE_FORCE_CHARGE, force_charge, SCHEMA_CHARGE),
        (SERVICE_FORCE_DISCHARGE, force_discharge, SCHEMA_DISCHARGE),
        (SERVICE_HOLD_BATTERY, hold_battery, SCHEMA_HOLD),
        (SERVICE_CLEAR_OVERRIDE, clear_override, SCHEMA_CLEAR),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=schema)


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    for name in (
        SERVICE_SET_TOU_SCHEDULE,
        SERVICE_SET_OPERATING_MODE,
        SERVICE_FORCE_CHARGE,
        SERVICE_FORCE_DISCHARGE,
        SERVICE_HOLD_BATTERY,
        SERVICE_CLEAR_OVERRIDE,
    ):
        hass.services.async_remove(DOMAIN, name)
