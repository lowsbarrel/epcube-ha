from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from epcube_api import ModeConfig

from .const import DOMAIN
from .coordinator import EpCubeConfigEntry, EpCubeCoordinator
from .entity import EpCubeEntity


@dataclass(frozen=True, kw_only=True)
class EpCubeNumberDescription(NumberEntityDescription):
    value_fn: Callable[[ModeConfig], str | None]
    argument: str


NUMBERS: tuple[EpCubeNumberDescription, ...] = (
    EpCubeNumberDescription(
        key="self_consumption_reserve",
        translation_key="self_consumption_reserve",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.self_consumption_reserve_soc,
        argument="self_consumption",
    ),
    EpCubeNumberDescription(
        key="backup_reserve",
        translation_key="backup_reserve",
        # The device rejects a backup reserve below 50%, which would defeat the mode.
        native_min_value=50,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.backup_power_reserve_soc,
        argument="backup",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpCubeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(EpCubeNumber(coordinator, description) for description in NUMBERS)


class EpCubeNumberEntity(EpCubeEntity, NumberEntity):
    pass


class EpCubeNumber(EpCubeNumberEntity):
    _section = "mode"

    def __init__(
        self, coordinator: EpCubeCoordinator, description: EpCubeNumberDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._description = description

    @property
    @override
    def native_value(self) -> float | None:
        config = self.snapshot.mode
        raw = None if config is None else self._description.value_fn(config)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @override
    async def async_set_native_value(self, value: float) -> None:
        config = self.snapshot.mode
        if config is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="config_unavailable"
            )
        # onlySave, so adjusting a reserve never changes the operating mode.
        soc = int(value)
        device = self.coordinator.client.device
        if self._description.argument == "backup":
            call = device.set_reserve_soc(config, backup=soc)
        else:
            call = device.set_reserve_soc(config, self_consumption=soc)
        await self.coordinator.async_apply(call)
