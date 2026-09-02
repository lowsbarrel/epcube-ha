"""Health and connectivity flags."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from epcube_api import Snapshot

from .coordinator import EpCubeConfigEntry, EpCubeCoordinator
from .entity import EpCubeEntity


@dataclass(frozen=True, kw_only=True)
class EpCubeBinaryDescription(BinarySensorEntityDescription):
    """A flag and how to read it out of a snapshot."""

    is_on_fn: Callable[[Snapshot], bool | None]


BINARY_SENSORS: tuple[EpCubeBinaryDescription, ...] = (
    EpCubeBinaryDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.live.is_online,
    ),
    EpCubeBinaryDescription(
        key="fault",
        translation_key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.live.is_fault,
    ),
    EpCubeBinaryDescription(
        key="alert",
        translation_key="alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.live.is_alert,
    ),
    EpCubeBinaryDescription(
        key="grid_outage",
        translation_key="grid_outage",
        device_class=BinarySensorDeviceClass.PROBLEM,
        # gridLight is the app's own indicator for whether the grid is present.
        is_on_fn=lambda s: None if s.live.grid_light is None else str(s.live.grid_light) != "1",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpCubeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        EpCubeBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class EpCubeBinarySensor(EpCubeEntity, BinarySensorEntity):
    """One health flag."""

    entity_description: EpCubeBinaryDescription

    def __init__(
        self, coordinator: EpCubeCoordinator, description: EpCubeBinaryDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.snapshot)
