"""Services.

Six calls, in two groups.

Configuration writes the tariff calendar and the operating mode. Both go
through `SwitchModeRequest`, so they carry the whole configuration and cannot
reset a field by omitting it.

Battery control applies a temporary override and undoes it afterwards; the
mechanics and the restart guarantee live in `override.py`.

Every service targets a device, so a multi-system account addresses one at a
time. Services are registered once for the integration rather than per entry,
which is why the handlers resolve the entry from the call.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from epcube_api import EpCubeError, TouWindow, WorkMode

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

SCHEMA_TOU = vol.Schema(
    {
        **_TARGET,
        **{vol.Optional(key): vol.Any(cv.ensure_list, None) for key in WINDOW_KEYS},
        vol.Optional(ATTR_APPLY, default=False): cv.boolean,
    }
)

SCHEMA_MODE = vol.Schema(
    {**_TARGET, vol.Required(ATTR_MODE): vol.In(MODES), vol.Optional(ATTR_RESERVE_SOC): SOC}
)

SCHEMA_CHARGE = vol.Schema(
    {
        **_TARGET,
        vol.Required(ATTR_TARGET_SOC): SOC,
        vol.Optional(ATTR_DURATION): cv.positive_time_period,
    }
)

SCHEMA_DISCHARGE = vol.Schema(
    {
        **_TARGET,
        vol.Required(ATTR_TARGET_SOC): SOC,
        vol.Optional(ATTR_DURATION): cv.positive_time_period,
    }
)

SCHEMA_HOLD = vol.Schema({**_TARGET, vol.Optional(ATTR_DURATION): cv.positive_time_period})

SCHEMA_CLEAR = vol.Schema(_TARGET)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> EpCubeCoordinator:
    """Resolve the targeted device to its loaded coordinator."""
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
    """Accept either the API's own `HH:MM_HH:MM_price` strings or mappings.

    A mapping is the readable form for a YAML automation:
        peak:
          - {start: "08:00", end: "12:00", price: 0.31}
    """
    raw = call.data.get(key)
    if raw is None:
        return None

    windows: list[str] = []
    for item in raw:
        if isinstance(item, str):
            if TouWindow.parse(item) is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="bad_tou_window",
                    translation_placeholders={"window": item, "field": key},
                )
            windows.append(item)
            continue
        if isinstance(item, dict) and "start" in item and "end" in item:
            price = item.get("price")
            window = TouWindow(
                start=str(item["start"]),
                end=str(item["end"]),
                price=float(price) if price is not None else None,
            )
            windows.append(window.to_api())
            continue
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="bad_tou_window",
            translation_placeholders={"window": str(item), "field": key},
        )
    return windows


def _duration(call: ServiceCall) -> timedelta | None:
    return call.data.get(ATTR_DURATION)


async def _guarded(coro) -> None:
    """Surface an API failure as something Home Assistant can show a user."""
    try:
        await coro
    except EpCubeError as err:
        raise HomeAssistantError(str(err)) from err


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the services once for the integration."""
    if hass.services.has_service(DOMAIN, SERVICE_CLEAR_OVERRIDE):
        return

    async def set_tou_schedule(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        config = coordinator.data.mode
        if config is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="config_unavailable"
            )
        windows: dict[str, Any] = {key: _windows(call, key) for key in WINDOW_KEYS}
        await _guarded(
            coordinator.client.device.set_tou_schedule(
                config, apply=call.data[ATTR_APPLY], **windows
            )
        )
        await coordinator.async_request_refresh()

    async def set_operating_mode(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        config = coordinator.data.mode
        if config is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="config_unavailable"
            )

        mode = MODES[call.data[ATTR_MODE]]
        if mode is WorkMode.TIME_OF_USE and not config.has_tou_schedule:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_tou_schedule"
            )

        reserve = call.data.get(ATTR_RESERVE_SOC)
        if reserve is not None:
            # Reserve first, with onlySave, so the mode change lands on a device
            # that already holds the intended floor.
            field = "backup" if mode is WorkMode.BACKUP else "self_consumption"
            await _guarded(coordinator.client.device.set_reserve_soc(config, **{field: reserve}))
            config = await coordinator.client.device.mode(coordinator.device_id)

        await _guarded(coordinator.client.device.set_mode(config, mode))
        await coordinator.async_request_refresh()

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
    """Remove the services once the last config entry goes away."""
    for name in (
        SERVICE_SET_TOU_SCHEDULE,
        SERVICE_SET_OPERATING_MODE,
        SERVICE_FORCE_CHARGE,
        SERVICE_FORCE_DISCHARGE,
        SERVICE_HOLD_BATTERY,
        SERVICE_CLEAR_OVERRIDE,
    ):
        hass.services.async_remove(DOMAIN, name)
