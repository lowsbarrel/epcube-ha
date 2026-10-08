from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from time import monotonic
from typing import Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from epcube_api import (
    EpCubeAsyncClient,
    EpCubeAuthError,
    EpCubeError,
    ModeConfig,
    Region,
    Snapshot,
)

from .battery import BatteryEnergyAccumulator
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

_SLOW_SECTIONS = ("detail", "network", "summary", "outages", "today", "month", "year", "lifetime")


class EpCubeCoordinator(DataUpdateCoordinator[Snapshot]):
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
        self._last_heavy: float | None = None
        self._slow_cache: dict[str, Any] = {}

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

        self.overrides = OverrideManager(hass, self, entry.entry_id)
        self._write_lock = asyncio.Lock()
        # The API's battery energy counters read zero, so derive from the stored-energy level.
        self.battery_energy = BatteryEnergyAccumulator()

    @override
    async def _async_update_data(self) -> Snapshot:
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
            # Tokens cannot be refreshed without the password, so surface the failure to the user.
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="token_expired"
            ) from err
        except EpCubeError as err:
            raise UpdateFailed(str(err)) from err

        if heavy_due:
            self._last_heavy = monotonic()
        self._carry_slow_sections(snapshot, heavy_due)
        self.battery_energy.update(snapshot.live.battery_current_electricity)

        if snapshot.errors:
            _LOGGER.debug(
                "refresh degraded, %s unavailable: %s",
                ", ".join(snapshot.errors),
                snapshot.errors,
            )
        return snapshot

    def _carry_slow_sections(self, snapshot: Snapshot, heavy_due: bool) -> None:
        for name in _SLOW_SECTIONS:
            if heavy_due and name not in snapshot.errors:
                self._slow_cache[name] = getattr(snapshot, name)
            elif name in self._slow_cache:
                setattr(snapshot, name, self._slow_cache[name])
                snapshot.errors.pop(name, None)

    @property
    def device_id(self) -> str:
        return self.data.dev_id

    async def async_write(self, write: Callable[[ModeConfig], Awaitable[object]]) -> None:
        async with self._write_lock:
            try:
                config = await self.client.device.mode(self.device_id)
                await write(config)
            except EpCubeAuthError as err:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="token_expired"
                ) from err
            except EpCubeError as err:
                raise HomeAssistantError(str(err)) from err
            await self.async_refresh()
