from __future__ import annotations

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from epcube_api import ModeConfig, WorkMode

from .const import DOMAIN
from .coordinator import EpCubeConfigEntry, EpCubeCoordinator
from .entity import EpCubeEntity

OPTIONS: dict[str, WorkMode] = {
    "self_consumption": WorkMode.SELF_CONSUMPTION,
    "time_of_use": WorkMode.TIME_OF_USE,
    "backup": WorkMode.BACKUP,
}
BY_MODE = {mode: slug for slug, mode in OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpCubeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EpCubeModeSelect(entry.runtime_data)])


class EpCubeModeSelect(EpCubeEntity, SelectEntity):
    _section = "mode"
    _attr_translation_key = "operating_mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EpCubeCoordinator) -> None:
        super().__init__(coordinator, "operating_mode")
        self._attr_options = list(OPTIONS)

    @property
    @override
    def current_option(self) -> str | None:
        config = self.snapshot.mode
        if config is None or config.mode is None:
            return None
        return BY_MODE.get(config.mode)

    @override
    async def async_select_option(self, option: str) -> None:
        mode = OPTIONS[option]
        device = self.coordinator.client.device

        async def write(config: ModeConfig) -> None:
            # Time-of-use with no tariff windows leaves an empty calendar; refuse the state.
            if mode is WorkMode.TIME_OF_USE and not config.has_tou_schedule:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="no_tou_schedule"
                )
            await device.set_mode(config, mode)

        await self.coordinator.async_write(write)
