"""Operating mode selection."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from epcube_api import WorkMode

from .const import DOMAIN
from .coordinator import EpCubeConfigEntry, EpCubeCoordinator
from .entity import EpCubeSectionEntity

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


class EpCubeModeSelect(EpCubeSectionEntity, SelectEntity):
    """Switch between self-consumption, time-of-use and backup."""

    _section = "mode"
    _attr_translation_key = "operating_mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EpCubeCoordinator) -> None:
        super().__init__(coordinator, "operating_mode")
        self._attr_options = list(OPTIONS)

    @property
    def current_option(self) -> str | None:
        config = self.snapshot.mode
        if config is None or config.mode is None:
            return None
        return BY_MODE.get(config.mode)

    async def async_select_option(self, option: str) -> None:
        config = self.snapshot.mode
        if config is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="config_unavailable"
            )

        mode = OPTIONS[option]
        # Time-of-use with no tariff windows configured leaves the battery on an
        # empty calendar, which behaves unpredictably. Refuse rather than let the
        # user reach that state from a dropdown.
        if mode is WorkMode.TIME_OF_USE and not config.has_tou_schedule:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_tou_schedule")

        await self.coordinator.async_apply(self.coordinator.client.device.set_mode(config, mode))
