from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, override

from homeassistant.components.sensor import (
    RestoreSensor,
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
from .entity import EpCubeEntity

type ValueFn = Callable[[Snapshot], StateType | datetime]


@dataclass(frozen=True, kw_only=True)
class EpCubeSensorDescription(SensorEntityDescription):
    value_fn: ValueFn
    section: str | None = None


def _power(key: str, name_key: str, value_fn: ValueFn) -> EpCubeSensorDescription:
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
    key: str, name_key: str, value_fn: ValueFn, *, section: str | None = None
) -> EpCubeSensorDescription:
    return EpCubeSensorDescription(
        key=key,
        translation_key=name_key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        # TOTAL_INCREASING: nightly resets must read as resets, not negative energy.
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=value_fn,
        section=section,
    )


SENSORS: tuple[EpCubeSensorDescription, ...] = (
    _power("solar_power", "solar_power", lambda s: s.solar_power_w),
    _power("grid_power", "grid_power", lambda s: s.live.grid_power),
    _power("load_power", "load_power", lambda s: s.live.load_power),
    _power("backup_power", "backup_power", lambda s: s.live.back_up_power),
    _power("non_backup_power", "non_backup_power", lambda s: s.live.non_back_up_power),
    _power("battery_power", "battery_power", lambda s: s.battery_power_w),
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
    _energy("solar_today", "solar_today", lambda s: s.live.solar_electricity),
    _energy("backup_today", "backup_today", lambda s: s.live.back_up_electricity),
    _energy(
        "house_consumption_today",
        "house_consumption_today",
        lambda s: s.live.load_electricity,
    ),
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
    # Naive but genuinely UTC: these fields match defCreateTime, which defTimeZone names UTC.
    return None if value is None else value.replace(tzinfo=UTC)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EpCubeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        EpCubeSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(EpCubeOverrideSensor(coordinator))
    entities.append(EpCubeBatteryEnergySensor(coordinator, "battery_charged_energy", "charged"))
    entities.append(
        EpCubeBatteryEnergySensor(coordinator, "battery_discharged_energy", "discharged")
    )

    pv = coordinator.data.pv
    if pv is not None:
        for string in pv.strings:
            entities.extend(
                EpCubePvSensor(coordinator, string.index, measure)
                for measure in ("power", "voltage", "current")
            )

    async_add_entities(entities)


class EpCubeSensorEntity(EpCubeEntity, SensorEntity):
    pass


class EpCubeSensor(EpCubeSensorEntity):
    def __init__(
        self, coordinator: EpCubeCoordinator, description: EpCubeSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._description = description
        self._section = description.section

    @property
    @override
    def native_value(self) -> StateType | datetime:
        return self._description.value_fn(self.snapshot)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self._description.key == "battery_power":
            measured = self.snapshot.series is not None and self.snapshot.series.latest()
            return {"source": "measured" if measured else "derived"}
        if self._description.key == "solar_power":
            return {"source": self.snapshot.solar_power_source}
        return None


class EpCubePvSensor(EpCubeSensorEntity):
    _MEASURES: ClassVar[dict[str, tuple[SensorDeviceClass, str, str, int]]] = {
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
    @override
    def available(self) -> bool:
        return (
            super().available and "pv" not in self.snapshot.errors and self.snapshot.pv is not None
        )

    @property
    @override
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


class EpCubeOverrideSensor(EpCubeSensorEntity):
    _attr_translation_key = "override"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EpCubeCoordinator) -> None:
        super().__init__(coordinator, "override")
        self._attr_options = ["none", "charge", "discharge", "hold"]

    @property
    @override
    def native_value(self) -> str:
        active = self.coordinator.overrides.active
        return active.kind if active else "none"

    @property
    @override
    def extra_state_attributes(self) -> dict[str, str] | None:
        active = self.coordinator.overrides.active
        if active is None:
            return None
        return {
            "target_soc": str(active.target_soc),
            "ends_at": active.ends_at.isoformat() if active.ends_at else "manual",
        }


class EpCubeBatteryEnergySensor(EpCubeSensorEntity, RestoreSensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: EpCubeCoordinator, key: str, direction: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._direction = direction
        self._restored = 0.0

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        value = last.native_value if last is not None else None
        if isinstance(value, (int, float, str)):
            try:
                self._restored = float(value)
            except TypeError, ValueError:
                self._restored = 0.0

    @property
    @override
    def native_value(self) -> float:
        session = getattr(self.coordinator.battery_energy, self._direction)
        return round(self._restored + session, 2)
