"""The EP Cube integration.

Talks to the EP Cube cloud API through `epcube_api`; this package is only the
Home Assistant glue - config entry lifecycle, a coordinator, and entities.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import EpCubeConfigEntry, EpCubeCoordinator
from .services import async_register_services, async_unregister_services


async def async_setup_entry(hass: HomeAssistant, entry: EpCubeConfigEntry) -> bool:
    """Set up EP Cube from a config entry."""
    coordinator = EpCubeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # After the first refresh: reverting a stale override needs device state.
    await coordinator.overrides.async_load()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EpCubeConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.overrides.async_unload()
        await entry.runtime_data.client.aclose()
        # Services belong to the integration, not the entry: drop them only when
        # the last system goes away.
        if not hass.config_entries.async_loaded_entries(DOMAIN):
            async_unregister_services(hass)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: EpCubeConfigEntry) -> None:
    """Reload when the options change, so a new interval takes effect at once."""
    await hass.config_entries.async_reload(entry.entry_id)
