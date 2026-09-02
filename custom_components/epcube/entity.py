"""Base entity: device identity and the availability rule."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from epcube_api import Snapshot

from .const import DOMAIN, MANUFACTURER
from .coordinator import EpCubeCoordinator


class EpCubeEntity(CoordinatorEntity[EpCubeCoordinator]):
    """Shared identity for every EP Cube entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EpCubeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        # The plant serial, not the numeric device id: the id is assigned by the
        # cloud and would change if the system were re-registered.
        self._attr_unique_id = f"{coordinator.serial}_{key}"

    @property
    def snapshot(self) -> Snapshot:
        return self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        snap = self.snapshot
        detail = snap.detail
        summary = snap.summary
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.serial)},
            manufacturer=MANUFACTURER,
            name="EP Cube",
            model=detail.model_type if detail else None,
            serial_number=self.coordinator.serial,
            sw_version=summary.software_version if summary else None,
            hw_version=summary.device_system_type if summary else None,
            configuration_url="https://www.epcube.com/",
        )


class EpCubeSectionEntity(EpCubeEntity):
    """An entity backed by an optional snapshot section.

    Supplementary reads are best-effort, so an entity fed by one goes
    unavailable when its section is missing rather than reporting a stale value
    as current.
    """

    _section: str

    @property
    def available(self) -> bool:
        return super().available and self._section not in self.snapshot.errors
