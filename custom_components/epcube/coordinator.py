"""The polling coordinator.

A fast loop refreshes live state every update interval; the heavy history reads
run on their own slower loop, so the platforms get responsive live values without
hammering a cloud API that has no published rate limit. Entities never issue
their own requests. `EpCubeAsyncClient.snapshot` already treats the live read as
the only mandatory one; this wraps that in Home Assistant's failure semantics and
gates the heavy reads by cadence.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from epcube_api import (
    EnergyTotals,
    EpCubeAsyncClient,
    EpCubeAuthError,
    EpCubeError,
    Region,
    Snapshot,
)

from .const import (
    CONF_ENABLE_SERIES,
    CONF_ENABLE_STATISTICS,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SN,
    CONF_STATISTICS_INTERVAL,
    CONF_TOKEN,
    DEFAULT_ENABLE_SERIES,
    DEFAULT_ENABLE_STATISTICS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATISTICS_INTERVAL,
    DOMAIN,
)
from .override import OverrideManager

_LOGGER = logging.getLogger(__name__)

type EpCubeConfigEntry = ConfigEntry[EpCubeCoordinator]

# The slowly-changing aggregates, carried across fast cycles so their sensors
# hold their last value instead of blanking between statistics-loop runs.
_TOTALS_SECTIONS = ("today", "month", "year", "lifetime")


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
        # The fast loop reads live state; the heavy history reads run at most once
        # per statistics_interval. None until the first run, which always fetches.
        self._last_heavy: float | None = None
        self._totals_cache: dict[str, EnergyTotals] = {}

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

    async def _async_update_data(self) -> Snapshot:
        # The heavy history reads (totals + series) are due on the first refresh
        # and then once per statistics_interval; every other cycle is live-only.
        heavy_due = (
            self._last_heavy is None or monotonic() - self._last_heavy >= self.statistics_interval
        )
        try:
            snapshot = await self.client.snapshot(
                self.serial,
                include_series=self.include_series and heavy_due,
                include_totals=self.include_statistics and heavy_due,
                include_outages=True,
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
        self._apply_totals_cache(snapshot)

        # A degraded section is not a failed refresh: the live data is present
        # and the affected entities simply hold their previous value.
        if snapshot.errors:
            _LOGGER.debug(
                "refresh degraded, %s unavailable: %s",
                ", ".join(snapshot.errors),
                snapshot.errors,
            )
        return snapshot

    def _apply_totals_cache(self, snapshot: Snapshot) -> None:
        """Serve the last good totals on cycles that did not read them.

        A fresh aggregate refreshes the cache; its absence - whether because this
        was a live-only cycle or the heavy read failed - is filled from the cache
        so the energy-dashboard sensors keep their value instead of going
        unavailable. Only the totals are cached: the series is left to fall back
        to the live-derived battery power, which stays current every cycle.
        """
        for name in _TOTALS_SECTIONS:
            fresh: EnergyTotals | None = getattr(snapshot, name)
            if fresh is not None:
                self._totals_cache[name] = fresh
            elif name in self._totals_cache:
                setattr(snapshot, name, self._totals_cache[name])
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
