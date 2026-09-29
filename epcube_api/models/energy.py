from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Self

from pydantic import Field

from ..const import Scope
from .base import ApiFloat, ApiInt, ApiStr, EpCubeModel, to_int_enum


class _EnergyFields(EpCubeModel):
    grid_electricity: ApiFloat = None
    grid_electricity_from: ApiFloat = None
    grid_electricity_to: ApiFloat = None
    solar_electricity: ApiFloat = None
    solar_dc_electricity: ApiFloat = None
    solar_ac_electricity: ApiFloat = None
    generator_electricity: ApiFloat = None
    ev_electricity: ApiFloat = None
    non_back_up_electricity: ApiFloat = None
    back_up_electricity: ApiFloat = None
    battery_charge_electricity: ApiFloat = None
    battery_discharge_electricity: ApiFloat = None

    self_help_rate: ApiFloat = None
    tree_num: ApiFloat = None
    coal: ApiFloat = None
    has_value: ApiInt = None


class EnergyTotals(_EnergyFields):
    battery_soc: ApiInt = None
    backup_loads_mode: ApiInt = None

    @property
    def net_grid(self) -> float | None:
        if self.grid_electricity_from is None or self.grid_electricity_to is None:
            return None
        return self.grid_electricity_from - self.grid_electricity_to


class SeriesReading(_EnergyFields):
    id: ApiStr = None

    grid_power: ApiFloat = None
    solar_power: ApiFloat = None
    generator_power: ApiFloat = None
    ev_power: ApiFloat = None
    non_back_up_power: ApiFloat = None
    back_up_power: ApiFloat = None
    battery_power: ApiFloat = None
    battery_soc: ApiInt = None

    grid_total_power: ApiFloat = None
    grid_half_power: ApiFloat = None
    solar_flow: ApiFloat = None
    solar_ac_power: ApiFloat = None
    solar_dc_power: ApiFloat = None
    generator_flow_power: ApiFloat = None
    ev_flow_power: ApiFloat = None
    non_back_up_flow_power: ApiFloat = None
    back_up_flow_power: ApiFloat = None
    backup_loads_mode: ApiInt = None

    @staticmethod
    def _watts(value: float | None) -> float | None:
        return None if value is None else value * 1000.0

    @property
    def solar_power_w(self) -> float | None:
        return self._watts(self.solar_power)

    @property
    def grid_power_w(self) -> float | None:
        return self._watts(self.grid_power)

    @property
    def battery_power_w(self) -> float | None:
        if self.battery_power is None:
            return None
        return -self.battery_power * 1000.0

    @property
    def load_power_w(self) -> float | None:
        if self.back_up_power is None and self.non_back_up_power is None:
            return None
        return self._watts((self.back_up_power or 0.0) + (self.non_back_up_power or 0.0))

    _MEASUREMENTS = (
        "battery_power",
        "battery_soc",
        "solar_power",
        "grid_power",
        "back_up_power",
        "non_back_up_power",
        "solar_electricity",
        "grid_electricity",
        "grid_electricity_from",
        "grid_electricity_to",
        "back_up_electricity",
        "battery_charge_electricity",
        "battery_discharge_electricity",
    )

    @property
    def is_empty(self) -> bool:
        if self.id is not None:
            return False
        return not any(getattr(self, name, None) for name in self._MEASUREMENTS)


class SeriesPoint(EpCubeModel):
    node_name: ApiStr = None
    scope_type: ApiStr = None
    node_vo: SeriesReading = Field(default_factory=SeriesReading)

    @property
    def reading(self) -> SeriesReading:
        return self.node_vo

    def timestamp(self, queried: date | datetime) -> datetime | None:
        label = (self.node_name or "").strip()
        if not label:
            return None
        base = (
            queried
            if isinstance(queried, datetime)
            else datetime(queried.year, queried.month, queried.day)
        )
        scope = to_int_enum(Scope, self.scope_type)
        if scope is None:
            return None

        try:
            if scope is Scope.DAY:
                hour, minute = (int(part) for part in label.split(":"))
                # 24:00 is the end of the day, not the start of the next hour.
                if hour == 24:
                    return base.replace(hour=0, minute=0) + timedelta(days=1)
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if scope is Scope.MONTH:
                return base.replace(day=int(label), hour=0, minute=0, second=0, microsecond=0)
            if scope is Scope.YEAR:
                return base.replace(
                    month=int(label), day=1, hour=0, minute=0, second=0, microsecond=0
                )
            return datetime(int(label), 1, 1)
        except TypeError, ValueError:
            return None


class EnergySeries(EpCubeModel):
    scope: Scope
    queried: date
    points: list[SeriesPoint] = Field(default_factory=list)

    @classmethod
    def from_api(cls, payload: Any, *, scope: Scope, queried: date) -> Self:
        points = [SeriesPoint.model_validate(item) for item in payload or []]
        return cls(scope=scope, queried=queried, points=points)

    def __len__(self) -> int:
        return len(self.points)

    # pydantic's BaseModel.__iter__ yields (field, value) pairs; iterate .points instead
    def __getitem__(self, index: int) -> SeriesPoint:
        return self.points[index]

    @property
    def granularity(self) -> str:
        return self.scope.series_granularity

    def populated(self) -> list[SeriesPoint]:
        return [p for p in self.points if not p.node_vo.is_empty]

    def timeline(self, field: str) -> list[tuple[datetime, float]]:
        out: list[tuple[datetime, float]] = []
        for point in self.points:
            if point.node_vo.is_empty:
                continue
            when = point.timestamp(self.queried)
            value = getattr(point.node_vo, field, None)
            if when is not None and value is not None:
                out.append((when, float(value)))
        return out

    def latest(self) -> SeriesPoint | None:
        populated = self.populated()
        return populated[-1] if populated else None
