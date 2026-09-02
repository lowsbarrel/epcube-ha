"""The polling coordinator.

One refresh gathers everything the platforms need, so entities never issue their
own requests. `EpCubeAsyncClient.snapshot` already treats the live read as the
only mandatory one; this wraps that in Home Assistant's failure semantics.
"""

from __future__ import annotations

import logging
from datetime import timedelta

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

from .const import (
    CONF_ENABLE_SERIES,
    CONF_ENABLE_STATISTICS,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SN,
    CONF_TOKEN,
    DEFAULT_ENABLE_SERIES,
    DEFAULT_ENABLE_STATISTICS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type EpCubeConfigEntry = ConfigEntry[EpCubeCoordinator]


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

    async def _async_update_data(self) -> Snapshot:
        try:
            snapshot = await self.client.snapshot(
                self.serial,
                include_series=self.include_series,
                include_totals=self.include_statistics,
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

        # A degraded section is not a failed refresh: the live data is present
        # and the affected entities simply hold their previous value.
        if snapshot.errors:
            _LOGGER.debug(
                "refresh degraded, %s unavailable: %s",
                ", ".join(snapshot.errors),
                snapshot.errors,
            )
        return snapshot

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
