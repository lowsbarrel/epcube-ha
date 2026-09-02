"""Sensors.

Most are described declaratively below; the PV-string sensors are built at setup
from whatever inputs the inverter actually reports, since the API does not
declare how many there are.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from epcube_api import Snapshot

from .coordinator import EpCubeConfigEntry, EpCubeCoordinator
from .entity import EpCubeEntity, EpCubeSectionEntity


@dataclass(frozen=True, kw_only=True)
class EpCubeSensorDescription(SensorEntityDescription):
    """A sensor and how to pull its value out of a snapshot."""

    value_fn: Callable[[Snapshot], StateType | datetime]
    section: str | None = None
    """Snapshot section this depends on; the entity is unavailable without it."""


def _power(key: str, name_key: str, value_fn) -> EpCubeSensorDescription:
    return EpCubeSensorDescription(
        key=key,
        translation_key=name_key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=value_fn,
    )


def _energy(
    key: str, name_key: str, value_fn, *, section: str | None = None
) -> EpCubeSensorDescription:
    return EpCubeSensorDescription(
        key=key,
        translation_key=name_key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        # TOTAL_INCREASING, not TOTAL: these counters reset at midnight, and the
        # energy dashboard needs to know that a drop is a reset, not a negative
        # reading.
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=value_fn,
        section=section,
    )


SENSORS: tuple[EpCubeSensorDescription, ...] = (
    # --- live power ---
    # Not live.solar_power: that field disagrees with both the per-string
    # endpoint and the series, which agree with each other. See
    # Snapshot.solar_power_w.
    _power("solar_power", "solar_power", lambda s: s.solar_power_w),
    _power("grid_power", "grid_power", lambda s: s.live.grid_power),
    _power("load_power", "load_power", lambda s: s.live.load_power),
    _power("backup_power", "backup_power", lambda s: s.live.back_up_power),
    _power("non_backup_power", "non_backup_power", lambda s: s.live.non_back_up_power),
    # Measured when the time series is enabled, derived otherwise; the attribute
    # on the entity says which, because the two differ in accuracy.
    _power("battery_power", "battery_power", lambda s: s.battery_power_w),
    # --- battery ---
    EpCubeSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.live.battery_soc,
    ),
    EpCubeSensorDescription(
        key="battery_energy",
        translation_key="battery_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: s.live.battery_current_electricity,
    ),
    # --- today's energy ---
    _energy("solar_today", "solar_today", lambda s: s.live.solar_electricity),
    _energy("backup_today", "backup_today", lambda s: s.live.back_up_electricity),
    _energy(
        "grid_import_today",
        "grid_import_today",
        lambda s: s.today.grid_electricity_from if s.today else None,
        section="today",
    ),
    _energy(
        "grid_export_today",
        "grid_export_today",
        lambda s: s.today.grid_electricity_to if s.today else None,
        section="today",
    ),
    _energy(
        "battery_charged_today",
        "battery_charged_today",
        lambda s: s.today.battery_charge_electricity if s.today else None,
        section="today",
    ),
    _energy(
        "battery_discharged_today",
        "battery_discharged_today",
        lambda s: s.today.battery_discharge_electricity if s.today else None,
        section="today",
    ),
    # --- lifetime ---
    _energy(
        "solar_lifetime",
        "solar_lifetime",
        lambda s: s.lifetime.solar_electricity if s.lifetime else None,
        section="lifetime",
    ),
    _energy(
        "grid_import_lifetime",
        "grid_import_lifetime",
        lambda s: s.lifetime.grid_electricity_from if s.lifetime else None,
        section="lifetime",
    ),
    _energy(
        "grid_export_lifetime",
        "grid_export_lifetime",
        lambda s: s.lifetime.grid_electricity_to if s.lifetime else None,
        section="lifetime",
    ),
    # --- diagnostics ---
    EpCubeSensorDescription(
        key="self_sufficiency",
        translation_key="self_sufficiency",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s: s.live.self_help_rate,
    ),
    EpCubeSensorDescription(
        key="operating_mode",
        translation_key="operating_mode",
        device_class=SensorDeviceClass.ENUM,
        options=["self_consumption", "time_of_use", "backup", "unknown"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _MODE_SLUGS.get(str(s.live.work_status), "unknown"),
    ),
    EpCubeSensorDescription(
        key="signal_level",
        translation_key="signal_level",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.live.signal_level,
    ),
    EpCubeSensorDescription(
        key="outage_count",
        translation_key="outage_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.live.grid_power_failure_num,
    ),
    EpCubeSensorDescription(
        key="last_outage",
        translation_key="last_outage",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        section="outages",
        value_fn=lambda s: _utc(s.outages[-1].start_time) if s.outages else None,
    ),
    EpCubeSensorDescription(
        key="last_connected",
        translation_key="last_connected",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        section="summary",
        value_fn=lambda s: _utc(s.summary.last_connect_time) if s.summary else None,
    ),
    EpCubeSensorDescription(
        key="wifi_ssid",
        translation_key="wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        section="network",
        value_fn=lambda s: s.network.wifi_name if s.network else None,
    ),
)

_MODE_SLUGS = {"1": "self_consumption", "2": "time_of_use", "3": "backup"}


def _utc(value: datetime | None) -> datetime | None:
    """Anchor a naive API timestamp to UTC.

    Home Assistant rejects naive datetimes on a timestamp sensor, and these
    particular fields really are UTC: deviceList.lastConnectTime matches
    homeDeviceInfo.defCreateTime exactly, and defTimeZone names that one UTC.
    The site-local copy (fromCreateTime) differs by the site's offset.
    """
    return None if value is None else value.replace(tzinfo=UTC)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpCubeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        EpCubeSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(EpCubeOverrideSensor(coordinator))

    # PV strings: the API does not declare how many inputs exist, so create one
    # set of entities per string actually reported at setup.
    pv = coordinator.data.pv
    if pv is not None:
        for string in pv.strings:
            entities.extend(
                EpCubePvSensor(coordinator, string.index, measure)
                for measure in ("power", "voltage", "current")
            )

    async_add_entities(entities)


class EpCubeSensor(EpCubeSectionEntity, SensorEntity):
    """A sensor described by an `EpCubeSensorDescription`."""

    entity_description: EpCubeSensorDescription

    def __init__(
        self, coordinator: EpCubeCoordinator, description: EpCubeSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._section = description.section or ""

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        # Solar and battery power each have several possible sources of differing
        # accuracy, so the entity says which one it used.
        if self.entity_description.key == "battery_power":
            measured = self.snapshot.series is not None and self.snapshot.series.latest()
            return {"source": "measured" if measured else "derived"}
        if self.entity_description.key == "solar_power":
            return {"source": self.snapshot.solar_power_source}
        return None


class EpCubePvSensor(EpCubeEntity, SensorEntity):
    """One measurement of one PV string."""

    _MEASURES: ClassVar[dict[str, tuple]] = {
        "power": (
            SensorDeviceClass.POWER,
            UnitOfPower.WATT,
            "pv_string_power",
            0,
        ),
        "voltage": (
            SensorDeviceClass.VOLTAGE,
            UnitOfElectricPotential.VOLT,
            "pv_string_voltage",
            1,
        ),
        "current": (
            SensorDeviceClass.CURRENT,
            UnitOfElectricCurrent.AMPERE,
            "pv_string_current",
            2,
        ),
    }

    def __init__(self, coordinator: EpCubeCoordinator, index: int, measure: str) -> None:
        super().__init__(coordinator, f"pv{index}_{measure}")
        device_class, unit, translation_key, precision = self._MEASURES[measure]
        self._index = index
        self._measure = measure
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = precision
        self._attr_translation_key = translation_key
        self._attr_translation_placeholders = {"index": str(index)}

    @property
    def available(self) -> bool:
        return (
            super().available and "pv" not in self.snapshot.errors and self.snapshot.pv is not None
        )

    @property
    def native_value(self) -> StateType:
        pv = self.snapshot.pv
        if pv is None:
            return None
        string = next((s for s in pv.strings if s.index == self._index), None)
        if string is None:
            return None
        if self._measure == "power":
            return string.power_w
        return getattr(string, self._measure)


class EpCubeOverrideSensor(EpCubeEntity, SensorEntity):
    """Which temporary override is running, if any.

    Without this an override is invisible: the reserve slider simply moves and
    nothing says why, or when it will move back.
    """

    _attr_translation_key = "override"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EpCubeCoordinator) -> None:
        super().__init__(coordinator, "override")
        self._attr_options = ["none", "charge", "discharge", "hold"]

    @property
    def native_value(self) -> str:
        override = self.coordinator.overrides.active
        return override.kind if override else "none"

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        override = self.coordinator.overrides.active
        if override is None:
            return None
        return {
            "target_soc": str(override.target_soc),
            "ends_at": override.ends_at.isoformat() if override.ends_at else "manual",
        }
