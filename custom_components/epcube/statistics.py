"""Import the device's own energy history into Home Assistant's statistics.

The Energy dashboard is drawn from HA's long-term statistics, which only hold
what HA recorded live - so every day before the integration was installed is
blank. The device keeps a per-day history (the MONTH-scope series), and this
imports it so those past days appear on the dashboard.

The history is written as **external** statistics (`epcube:*`), not into the
live sensors' own ids: a live sensor is `TOTAL_INCREASING`, and the recorder
derives its `sum` from a baseline set at midnight of the install day. Injecting
older, larger sums into that same series would collide with that baseline. A
separate statistic id owns one clean, self-consistent history end to end - past
(backfilled once on setup) and present (refreshed each statistics-loop run). The
user points the Energy dashboard's sources at these `epcube:*` ids.

The API only resolves daily granularity for past days (MONTH scope = one point
per day), so the import is one point per local day; that is exactly what the
Energy dashboard's daily bars need.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfEnergy
from homeassistant.util import dt as dt_util

from epcube_api import EnergySeries, EpCubeError, Scope

if TYPE_CHECKING:
    from .coordinator import EpCubeCoordinator

_LOGGER = logging.getLogger(__name__)

# metric key -> (SeriesReading field, name shown in the Energy source picker).
# Only the flows the API actually populates: battery in/out come back as 0 at
# every scope, so there is nothing to import for them.
_METRICS: dict[str, tuple[str, str]] = {
    "solar": ("solar_electricity", "EP Cube solar (imported)"),
    "grid_import": ("grid_electricity_from", "EP Cube grid import (imported)"),
    "grid_export": ("grid_electricity_to", "EP Cube grid export (imported)"),
}

# How far back to look for history. The loop stops at the first month with no
# data, so this is only a floor on a pathological account.
_MAX_MONTHS = 60


def _cumulative_points(daily: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """Turn per-day energy into cumulative boundary points.

    A point at day D carries the sum accumulated *before* D, so the Energy
    dashboard reads day D as `sum(D+1) - sum(D)` = that day's energy. A trailing
    point one day past the last carries the final total, so the last day counts.
    `daily` must be sorted ascending.
    """
    points: list[tuple[date, float]] = []
    running = 0.0
    for day, value in daily:
        points.append((day, round(running, 3)))
        running += value
    if daily:
        points.append((daily[-1][0] + timedelta(days=1), round(running, 3)))
    return points


class StatisticsImporter:
    """Owns the imported energy history for one system."""

    def __init__(self, coordinator: EpCubeCoordinator) -> None:
        self._c = coordinator
        # metric -> {local day -> that day's energy, kWh}
        self._daily: dict[str, dict[date, float]] = {key: {} for key in _METRICS}
        self._lock = asyncio.Lock()

    def _statistic_id(self, metric: str) -> str:
        return f"epcube:{self._c.serial.lower()}_{metric}"

    async def async_backfill(self, dev_id: str) -> None:
        """Pull the whole device history and import it. Run once on setup."""
        async with self._lock:
            month = dt_util.now().date().replace(day=1)
            for _ in range(_MAX_MONTHS):
                try:
                    series = await self._c.client.data.series(dev_id, Scope.MONTH, month)
                except EpCubeError as err:
                    _LOGGER.debug("history backfill stopped at %s: %s", month, err)
                    break
                if not self._absorb(series):
                    break
                month = (month - timedelta(days=1)).replace(day=1)
            self._import_all()

    async def async_refresh(self, dev_id: str) -> None:
        """Refresh the current month and re-import. Run each statistics cycle."""
        async with self._lock:
            month = dt_util.now().date().replace(day=1)
            series = await self._c.client.data.series(dev_id, Scope.MONTH, month)
            self._absorb(series)
            self._import_all()

    def _absorb(self, series: EnergySeries) -> bool:
        """Record a MONTH-scope series' per-day values. Returns whether the
        month held any data - the backfill uses that to know when to stop."""
        found = False
        for metric, (field, _name) in _METRICS.items():
            for when, value in series.timeline(field):
                self._daily[metric][when.date()] = value
                found = True
        return found

    def _import_all(self) -> None:
        for metric, (_field, name) in _METRICS.items():
            day_map = self._daily[metric]
            if not day_map:
                continue
            points = _cumulative_points(sorted(day_map.items()))
            metadata = StatisticMetaData(
                has_mean=False,
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=name,
                source="epcube",
                statistic_id=self._statistic_id(metric),
                unit_class="energy",
                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            )
            stats = [
                StatisticData(start=dt_util.start_of_local_day(day), state=total, sum=total)
                for day, total in points
            ]
            async_add_external_statistics(self._c.hass, metadata, stats)
