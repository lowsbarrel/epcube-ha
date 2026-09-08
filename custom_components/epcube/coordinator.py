"""The polling coordinator.

A fast loop refreshes the live tier (live, mode, PV) every update interval; the
heavy reads (device config, outages and history) run on their own slower loop, so
the platforms get responsive live values without hammering a cloud API that has
no published rate limit. Entities never issue their own requests.
`EpCubeAsyncClient.snapshot` already treats the live read as the only mandatory
one; this wraps that in Home Assistant's failure semantics and gates the heavy
reads by cadence.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from epcube_api import (
    EpCubeAsyncClient,
    EpCubeAuthError,
    EpCubeError,
    Region,
    Snapshot,
)

from .battery import BatteryEnergyAccumulator
from .const import (
    CONF_ENABLE_SERIES,
    CONF_ENABLE_STATISTICS,
    CONF_IMPORT_HISTORY,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SN,
    CONF_STATISTICS_INTERVAL,
    CONF_TOKEN,
    DEFAULT_ENABLE_SERIES,
    DEFAULT_ENABLE_STATISTICS,
    DEFAULT_IMPORT_HISTORY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATISTICS_INTERVAL,
    DOMAIN,
)
from .override import OverrideManager
from .statistics import StatisticsImporter

_LOGGER = logging.getLogger(__name__)

type EpCubeConfigEntry = ConfigEntry[EpCubeCoordinator]

# Sections read only on the heavy loop, carried across the live-only cycles so
# their entities hold their last value instead of blanking between runs. The live
# tier (live, mode, PV) is read every cycle and never cached; the series is also
# left uncached, so battery power falls back to the current live-derived value.
_SLOW_SECTIONS = ("detail", "network", "summary", "outages", "today", "month", "year", "lifetime")


class EpCubeCoordinator(DataUpdateCoordinator[Snapshot]):
    """Polls one EP Cube system and shares the result with every platform."""

    config_entry: EpCubeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EpCubeConfigEntry) -> None:
        options = entry.options
        self.serial: str = entry.data[CONF_SN]
        self.include_series: bool = options.get(CONF_ENABLE_SERIES, DEFAULT_ENABLE_SERIES)
        self.include_statistics: bool = options.get(
            CONF_ENABLE_STATISTICS, DEFAULT_ENABLE_STATISTICS
        )
        self.statistics_interval: float = options.get(
            CONF_STATISTICS_INTERVAL, DEFAULT_STATISTICS_INTERVAL
        )
        self.import_history: bool = options.get(CONF_IMPORT_HISTORY, DEFAULT_IMPORT_HISTORY)
        # The fast loop reads the live tier; the heavy reads run at most once per
        # statistics_interval. None until the first run, which always fetches.
        self._last_heavy: float | None = None
        self._slow_cache: dict[str, Any] = {}

        # Home Assistant's shared httpx client: connection pooling and a single
        # place where proxy and TLS settings are configured.
        self.client = EpCubeAsyncClient(
            region=Region.parse(entry.data[CONF_REGION]),
            token=entry.data[CONF_TOKEN],
            http_client=get_async_client(hass),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

        self.overrides = OverrideManager(hass, self)
        self.statistics = StatisticsImporter(self)
        # The API's battery energy counters read zero, so derive them by tracking
        # the stored-energy level, which the live read carries every fast cycle.
        self.battery_energy = BatteryEnergyAccumulator()

    async def _async_update_data(self) -> Snapshot:
        # The heavy reads (device config, outages and history) are due on the
        # first refresh and then once per statistics_interval; every other cycle
        # reads only the live tier - live, mode and PV.
        heavy_due = (
            self._last_heavy is None or monotonic() - self._last_heavy >= self.statistics_interval
        )
        try:
            snapshot = await self.client.snapshot(
                self.serial,
                include_config=heavy_due,
                include_series=self.include_series and heavy_due,
                include_totals=self.include_statistics and heavy_due,
                include_outages=heavy_due,
            )
        except EpCubeAuthError as err:
            # Tokens expire and cannot be refreshed without the password, so this
            # has to reach the user rather than retry forever.
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="token_expired"
            ) from err
        except EpCubeError as err:
            raise UpdateFailed(str(err)) from err

        if heavy_due:
            self._last_heavy = monotonic()
        self._carry_slow_sections(snapshot, heavy_due)
        self.battery_energy.update(snapshot.live.battery_current_electricity)

        if heavy_due and self.import_history:
            try:
                await self.statistics.async_refresh(snapshot.dev_id)
            except Exception as err:  # a stats import must never fail the poll
                _LOGGER.warning("energy history import failed: %s", err)

        # A degraded section is not a failed refresh: the live data is present
        # and the affected entities simply hold their previous value.
        if snapshot.errors:
            _LOGGER.debug(
                "refresh degraded, %s unavailable: %s",
                ", ".join(snapshot.errors),
                snapshot.errors,
            )
        return snapshot

    def _carry_slow_sections(self, snapshot: Snapshot, heavy_due: bool) -> None:
        """Keep the slow sections steady across live-only cycles.

        On a heavy cycle each freshly read section refreshes the cache, and one
        that failed keeps its last good value rather than the error; on a
        live-only cycle the cache is served verbatim. This holds the energy and
        device entities at their last value between statistics runs instead of
        blanking them. The series is deliberately not cached: its battery power
        falls back to the live-derived value, which is current every cycle.
        """
        for name in _SLOW_SECTIONS:
            if heavy_due and name not in snapshot.errors:
                self._slow_cache[name] = getattr(snapshot, name)
            elif name in self._slow_cache:
                setattr(snapshot, name, self._slow_cache[name])
                snapshot.errors.pop(name, None)

    @property
    def device_id(self) -> str:
        """The numeric device id, which every write needs."""
        return self.data.dev_id

    async def async_apply(self, coro) -> None:
        """Run a write, then refresh so the UI reflects it.

        Writes are slow to take effect on the device, so the refresh that follows
        may still report the old value; the next poll settles it.
        """
        try:
            await coro
        except EpCubeAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="token_expired"
            ) from err
        except EpCubeError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()
