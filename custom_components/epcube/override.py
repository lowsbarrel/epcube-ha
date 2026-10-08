from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from epcube_api import ModeConfig

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import EpCubeCoordinator

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1

CHARGE = "charge"
DISCHARGE = "discharge"
HOLD = "hold"


@dataclass(slots=True)
class Override:
    kind: str
    target_soc: int | None
    ends_at: datetime | None
    previous_reserve: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target_soc": self.target_soc,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "previous_reserve": self.previous_reserve,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Override | None:
        if not raw or not raw.get("kind"):
            return None
        ends_at = raw.get("ends_at")
        previous = raw.get("previous_reserve")
        if previous is None:
            previous = (raw.get("baseline") or {}).get("selfConsumptioinReserveSoc")
        return cls(
            kind=raw["kind"],
            target_soc=raw.get("target_soc"),
            ends_at=dt_util.parse_datetime(ends_at) if ends_at else None,
            previous_reserve=previous,
        )

    @property
    def expired(self) -> bool:
        return self.ends_at is not None and self.ends_at <= dt_util.utcnow()


class OverrideManager:
    def __init__(self, hass: HomeAssistant, coordinator: EpCubeCoordinator, entry_id: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry_id}.override"
        )
        self.active: Override | None = None
        self._cancel_timer: Any = None

    async def async_load(self) -> None:
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
            try:
                await self.async_clear()
            except HomeAssistantError as err:
                raise ConfigEntryNotReady(str(err)) from err
        else:
            _LOGGER.info("resuming override %s until %s", override.kind, override.ends_at)
            self._arm(override.ends_at)

    @callback
    def async_unload(self) -> None:
        # The override stays on disk: a reload must not abandon the promise to revert.
        self._disarm()

    async def async_start(
        self,
        kind: str,
        *,
        target_soc: int | None = None,
        duration: timedelta | None = None,
    ) -> None:
        current_soc = self.coordinator.data.battery_soc

        if kind == HOLD:
            if current_soc is None:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="soc_unknown")
            reserve = current_soc
        else:
            reserve = self._require_target(target_soc)

        previous = self.active.previous_reserve if self.active is not None else None
        captured: dict[str, str | None] = {}

        async def write(config: ModeConfig) -> None:
            # Snapshot only before the first write: re-overriding must not record the override.
            if self.active is None:
                captured["reserve"] = config.self_consumption_reserve_soc
            await self.coordinator.client.device.set_reserve_soc(config, self_consumption=reserve)

        await self.coordinator.async_write(write)
        if captured:
            previous = captured["reserve"]

        ends_at = dt_util.utcnow() + duration if duration is not None else None
        self.active = Override(
            kind=kind, target_soc=reserve, ends_at=ends_at, previous_reserve=previous
        )
        await self._store.async_save(self.active.as_dict())
        self._arm(ends_at)

        _LOGGER.info(
            "override %s: reserve %s%%, until %s", kind, reserve, ends_at or "cleared manually"
        )

    async def async_clear(self) -> None:
        override = self.active
        if override is None:
            return

        self._disarm()
        if override.previous_reserve is not None:
            try:
                await self.coordinator.async_write(
                    lambda config: self.coordinator.client.device.set_reserve_soc(
                        config, self_consumption=int(override.previous_reserve)
                    )
                )
            except HomeAssistantError:
                _LOGGER.warning(
                    "could not restore reserve for override %s; retrying in 5 minutes",
                    override.kind,
                )
                self._arm(dt_util.utcnow() + timedelta(minutes=5))
                raise

        self.active = None
        await self._store.async_remove()
        _LOGGER.info("override %s cleared, previous reserve restored", override.kind)

    def _require_target(self, target_soc: int | None) -> int:
        if target_soc is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="target_soc_required"
            )
        return target_soc

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
