from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EpCubeConfigEntry, EpCubeCoordinator
from .entity import EpCubeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpCubeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EpCubeGridChargingSwitch(entry.runtime_data)])


class EpCubeSwitchEntity(EpCubeEntity, SwitchEntity):
    pass


class EpCubeGridChargingSwitch(EpCubeSwitchEntity):
    _section = "mode"
    _attr_translation_key = "grid_charging"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EpCubeCoordinator) -> None:
        super().__init__(coordinator, "grid_charging")

    @property
    @override
    def is_on(self) -> bool | None:
        config = self.snapshot.mode
        return None if config is None else config.grid_charging_allowed

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, allowed: bool) -> None:
        config = self.snapshot.mode
        if config is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="config_unavailable"
            )

        await self.coordinator.async_apply(
            self.coordinator.client.device.set_grid_charging(config, allowed)
        )

        # Some devices accept this write with HTTP 200 but keep the old value, so read back.
        applied = self.snapshot.mode
        if applied is not None and applied.grid_charging_allowed is not allowed:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="grid_charging_rejected"
            )
