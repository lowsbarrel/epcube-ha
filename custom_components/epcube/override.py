from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from epcube_api import EpCubeError, ModeConfig, SwitchModeRequest

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
    baseline: dict[str, Any] = field(default_factory=dict)

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
            await self.async_clear()
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
        config = self._config()
        current_soc = self.coordinator.data.battery_soc

        if kind == HOLD:
            if current_soc is None:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="soc_unknown")
            reserve = current_soc
        else:
            reserve = self._require_target(target_soc)

        # Snapshot only before the first write: re-overriding must not record the override.
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
        self._disarm()
        override, self.active = self.active, None
        await self._store.async_remove()

        if override is None or not override.baseline:
            return

        await self._send_payload(override.baseline)
        _LOGGER.info("override %s cleared, previous settings restored", override.kind)
        await self.coordinator.async_request_refresh()

    def _require_target(self, target_soc: int | None) -> int:
        if target_soc is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="target_soc_required"
            )
        return target_soc

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
