from __future__ import annotations

from typing import override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from epcube_api import Snapshot

from .const import DOMAIN, MANUFACTURER
from .coordinator import EpCubeCoordinator


class EpCubeEntity(CoordinatorEntity[EpCubeCoordinator]):
    _attr_has_entity_name = True
    _section: str | None = None

    def __init__(self, coordinator: EpCubeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        # Plant serial, not the cloud-assigned device id, which changes on re-registration.
        self._attr_unique_id = f"{coordinator.serial}_{key}"

    @property
    def snapshot(self) -> Snapshot:
        return self.coordinator.data

    @property
    @override
    def available(self) -> bool:
        return super().available and self._section not in self.snapshot.errors

    @property
    @override
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
