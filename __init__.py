"""The Pitboss integration."""
from __future__ import annotations

from .pitboss_api import PitbossApi
from requests.exceptions import ConnectTimeout, HTTPError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import PitbossDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SWITCH
]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Pitboss from a config entry."""

    try:
        api = await hass.async_add_executor_job(PitbossApi, config_entry.data['host'])
    except (ConnectTimeout, HTTPError) as ex:
        raise ConfigEntryNotReady(
            f"Unable to connect to Pitboss Smoker: {ex}"
        ) from ex

    coordinator = PitbossDataUpdateCoordinator(hass, api, config_entry.data)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
