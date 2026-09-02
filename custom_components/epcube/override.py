"""Temporary battery overrides, and getting the device back afterwards.

The API has no forced-charge endpoint. What it has is a reserve state-of-charge
floor, and the device tracks it:

* **charge**  reserve above the current level. The device fills the battery up
  to the reserve, drawing from the grid if grid charging is permitted and the
  sun cannot manage it.
* **discharge**  reserve below the current level. The device supplies the house
  from the battery down to the reserve.
* **hold**  reserve at the current level. Neither direction, and the battery
  rides out the window at whatever it holds now.

Only the reserve is touched, and it is written with `onlySave`, so the operating
mode is never disturbed. No synthetic tariff windows, no mode flipping, nothing
that looks like a real user setting once it is undone.

`allowChargingXiaGrid` is deliberately *not* part of this. On the hardware this
was developed against the field is read-only: four payload shapes (onlySave 0
and 1, string and integer, and the correctly-spelled key alongside the API's
misspelling) were all accepted with HTTP 200 and none took effect. An override
that claimed to control grid charging would be lying, so it does not claim to.

The hard part is the undo. An override is a promise to put three fields back,
and the process holding that promise can be restarted at any moment. So the
baseline is written to disk before the override is applied, and reloaded on
startup: an override whose deadline has passed is reverted immediately, and one
still running gets its timer re-armed. A crash costs the remainder of a window,
never the settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from epcube_api import EpCubeError, ModeConfig, SwitchModeRequest

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1

CHARGE = "charge"
DISCHARGE = "discharge"
HOLD = "hold"


@dataclass(slots=True)
class Override:
    """An override in flight, and everything needed to undo it."""

    kind: str
    target_soc: int | None
    ends_at: datetime | None
    baseline: dict[str, Any] = field(default_factory=dict)
    """The complete switchMode payload as the device had it beforehand."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target_soc": self.target_soc,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "baseline": self.baseline,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Override | None:
        if not raw or not raw.get("kind"):
            return None
        ends_at = raw.get("ends_at")
        return cls(
            kind=raw["kind"],
            target_soc=raw.get("target_soc"),
            ends_at=dt_util.parse_datetime(ends_at) if ends_at else None,
            baseline=raw.get("baseline") or {},
        )

    @property
    def expired(self) -> bool:
        return self.ends_at is not None and self.ends_at <= dt_util.utcnow()


class OverrideManager:
    """Applies a temporary override and guarantees the revert."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{coordinator.config_entry.entry_id}.override"
        )
        self.active: Override | None = None
        self._cancel_timer: Any = None

    # -- lifecycle --

    async def async_load(self) -> None:
        """Restore any override that outlived the last run.

        Called during setup, after the first refresh, so the device state needed
        to revert is already available.
        """
        stored = await self._store.async_load()
        override = Override.from_dict(stored or {})
        if override is None:
            return

        self.active = override
        if override.expired:
            _LOGGER.info(
                "reverting an override that expired while Home Assistant was down (%s, due %s)",
                override.kind,
                override.ends_at,
            )
            await self.async_clear()
        else:
            _LOGGER.info("resuming override %s until %s", override.kind, override.ends_at)
            self._arm(override.ends_at)

    @callback
    def async_unload(self) -> None:
        """Drop the timer without touching the device.

        The override stays on disk deliberately: a reload must not silently
        abandon a promise to put the settings back.
        """
        self._disarm()

    # -- applying --

    async def async_start(
        self,
        kind: str,
        *,
        target_soc: int | None = None,
        duration: timedelta | None = None,
    ) -> None:
        """Apply an override, replacing any that is already running."""
        config = self._config()
        current_soc = self.coordinator.data.battery_soc

        if kind == HOLD:
            if current_soc is None:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="soc_unknown")
            reserve = int(current_soc)
        else:
            reserve = self._require_target(target_soc)

        # Snapshot before the first write, and only for the first: re-overriding
        # must not record an already-overridden state as the baseline.
        baseline = (
            self.active.baseline
            if self.active is not None and self.active.baseline
            else SwitchModeRequest.from_config(config, only_save=True).api_dump()
        )

        request = SwitchModeRequest.from_config(config, only_save=True).with_changes(
            self_consumption_reserve_soc=str(reserve)
        )
        await self._send(request)

        ends_at = dt_util.utcnow() + duration if duration else None
        self.active = Override(kind=kind, target_soc=reserve, ends_at=ends_at, baseline=baseline)
        await self._store.async_save(self.active.as_dict())
        self._arm(ends_at)

        _LOGGER.info(
            "override %s: reserve %s%%, until %s", kind, reserve, ends_at or "cleared manually"
        )
        await self.coordinator.async_request_refresh()

    async def async_clear(self) -> None:
        """Restore the settings the device had before the override."""
        self._disarm()
        override, self.active = self.active, None
        await self._store.async_remove()

        if override is None or not override.baseline:
            return

        # Replay the stored payload verbatim. It was captured as a complete
        # switchMode body precisely so the revert needs nothing from the device.
        await self._send_payload(override.baseline)
        _LOGGER.info("override %s cleared, previous settings restored", override.kind)
        await self.coordinator.async_request_refresh()

    # -- internals --

    def _require_target(self, target_soc: int | None) -> int:
        if target_soc is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="target_soc_required"
            )
        return int(target_soc)

    def _config(self) -> ModeConfig:
        config = self.coordinator.data.mode
        if config is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="config_unavailable"
            )
        return config

    async def _send(self, request: SwitchModeRequest) -> None:
        await self._send_payload(request.api_dump())

    async def _send_payload(self, payload: dict[str, Any]) -> None:
        try:
            await self.coordinator.client.raw.post("device/switchMode", body=payload)
        except EpCubeError as err:
            raise HomeAssistantError(str(err)) from err

    @callback
    def _arm(self, ends_at: datetime | None) -> None:
        self._disarm()
        if ends_at is None:
            return

        async def _revert(_now: datetime) -> None:
            _LOGGER.info("override window elapsed, reverting")
            await self.async_clear()

        self._cancel_timer = async_track_point_in_utc_time(self.hass, _revert, ends_at)

    @callback
    def _disarm(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
