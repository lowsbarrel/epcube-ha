"""Energy counters and time series.

Two endpoints, two shapes:

* `device/queryDataElectricityV2` -> one aggregate per call (`EnergyTotals`)
* `device/queryDataGraphV2`       -> a series of points (`EnergySeries`)

The series is the interesting one: at `Scope.DAY` it returns a reading every five
minutes from midnight, and unlike the live snapshot it reports **`battery_power`
directly** rather than leaving it to be inferred.

Beware a unit inconsistency in the API: the live snapshot reports power in watts,
the series reports the same quantities in kilowatts. `SeriesReading` keeps the
values as sent (kW) and exposes `*_w` properties for the conversion.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Self

from pydantic import Field

from ..const import Scope
from .base import ApiFloat, ApiInt, ApiStr, EpCubeModel


class _EnergyFields(EpCubeModel):
    """Energy counters, kWh. Shared by the aggregate and the series reading."""

    grid_electricity: ApiFloat = None
    grid_electricity_from: ApiFloat = None
    """Imported from the grid. Not present in the live snapshot."""
    grid_electricity_to: ApiFloat = None
    """Exported to the grid. Not present in the live snapshot."""
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
    """Self-sufficiency over the window, percent."""
    tree_num: ApiFloat = None
    """Marketing equivalence: trees' worth of CO2 avoided."""
    coal: ApiFloat = None
    """Marketing equivalence: kg of coal not burned."""
    has_value: ApiInt = None
    """Reads 0 even on points that carry data; not a usable emptiness flag.
    `SeriesReading.is_empty` uses `id` instead."""


class EnergyTotals(_EnergyFields):
    """One aggregate from `device/queryDataElectricityV2`.

    The power fields it also returns are zero for every historical window, so
    only the energy counters above are meaningful here.
    """

    battery_soc: ApiInt = None
    backup_loads_mode: ApiInt = None

    @property
    def net_grid(self) -> float | None:
        """Import minus export, kWh. Negative means a net exporter."""
        if self.grid_electricity_from is None or self.grid_electricity_to is None:
            return None
        return self.grid_electricity_from - self.grid_electricity_to


class SeriesReading(_EnergyFields):
    """The `nodeVo` of one series point: counters plus instantaneous power.

    Power values are **kilowatts**, unlike the live snapshot's watts.
    """

    id: ApiStr = None

    grid_power: ApiFloat = None
    solar_power: ApiFloat = None
    generator_power: ApiFloat = None
    ev_power: ApiFloat = None
    non_back_up_power: ApiFloat = None
    back_up_power: ApiFloat = None
    battery_power: ApiFloat = None
    """Battery power as the API sends it, kW: **negative = charging**.

    Established from the energy balance, which closes only with this sign:
    `solar + grid - load + battery == 0`. At 11:05 on a real system that was
    `1.05 + 0.00 - 0.11 + (-0.94) = 0.00` while the state of charge climbed.

    This is the opposite of `battery_power_w` and of `LiveSnapshot.battery_power`,
    both of which use positive = charging. Prefer those unless you specifically
    want the raw value.
    """
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
        """Battery power in watts, **positive = charging**.

        Negated relative to the raw field, so that every battery power in this
        package shares one convention.
        """
        if self.battery_power is None:
            return None
        return -self.battery_power * 1000.0

    @property
    def load_power_w(self) -> float | None:
        """Total house load, watts: backup plus non-backup circuits."""
        if self.back_up_power is None and self.non_back_up_power is None:
            return None
        return self._watts((self.back_up_power or 0.0) + (self.non_back_up_power or 0.0))

    # Fields that carry an actual measurement. Deliberately excludes
    # has_value (always 0) and backup_loads_mode (a constant), both of which
    # would make every point look populated.
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
        """True for a placeholder point the device had no data for.

        Neither obvious flag works. `has_value` reads 0 on every point of a
        real series, populated or not. `id` is present on day-scope points
        but absent from every month, year and lifetime point, so keying on it
        discards those series entirely. What is left is to ask whether any
        measurement is actually non-zero.
        """
        if self.id is not None:
            return False
        return not any(getattr(self, name, None) for name in self._MEASUREMENTS)


class SeriesPoint(EpCubeModel):
    """One point of a `device/queryDataGraphV2` series."""

    node_name: ApiStr = None
    """The x-axis label: `"09:45"` for a day, `"07"` for a month or year,
    `"2026"` for lifetime."""
    scope_type: ApiStr = None
    node_vo: SeriesReading = Field(default_factory=SeriesReading)
    """The readings. Named `nodeVo` by the API."""

    @property
    def reading(self) -> SeriesReading:
        """Readable alias for `node_vo`."""
        return self.node_vo

    def timestamp(self, queried: date | datetime) -> datetime | None:
        """Resolve this point's label to a real datetime.

        `queried` is the date the series was requested for; the label alone is
        ambiguous without it (`"07"` is a day in a month series and a month in a
        year series).
        """
        label = (self.node_name or "").strip()
        if not label:
            return None
        base = (
            queried
            if isinstance(queried, datetime)
            else datetime(queried.year, queried.month, queried.day)
        )
        try:
            scope = Scope(int(self.scope_type))  # ty: ignore[invalid-argument-type]
        except (TypeError, ValueError):
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
            # Scope.LIFETIME, the only one left: a bare year.
            return datetime(int(label), 1, 1)
        except (TypeError, ValueError):
            return None


class EnergySeries(EpCubeModel):
    """A parsed `device/queryDataGraphV2` response.

    The endpoint returns a bare list; this wrapper keeps the scope and the
    queried date alongside so points can resolve their own timestamps.
    """

    scope: Scope
    queried: date
    points: list[SeriesPoint] = Field(default_factory=list)

    @classmethod
    def from_api(cls, payload: Any, *, scope: Scope, queried: date) -> Self:
        points = [SeriesPoint.model_validate(item) for item in payload or []]
        return cls(scope=scope, queried=queried, points=points)

    def __len__(self) -> int:
        return len(self.points)

    # No __iter__: pydantic's BaseModel already defines one that yields
    # (field, value) pairs, and overriding it would break dict(series).
    # Iterate series.points instead.

    def __getitem__(self, index: int) -> SeriesPoint:
        return self.points[index]

    @property
    def granularity(self) -> str:
        """What one point covers, e.g. "five minutes"."""
        return self.scope.series_granularity

    def populated(self) -> list[SeriesPoint]:
        """Only the points the device actually has data for."""
        return [p for p in self.points if not p.node_vo.is_empty]

    def timeline(self, field: str) -> list[tuple[datetime, float]]:
        """`(timestamp, value)` pairs for one reading field, empties dropped.

        `field` is a `SeriesReading` attribute or property name, so both
        `"battery_power"` (kW, as sent) and `"battery_power_w"` (watts) work.
        """
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
        """The most recent point with data."""
        populated = self.populated()
        return populated[-1] if populated else None
