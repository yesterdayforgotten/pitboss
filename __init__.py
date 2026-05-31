"""The Pitboss integration."""

import logging

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DATA_DEVICE_INFO, DOMAIN, INFO_MAC, PLATFORMS
from .coordinator import PitbossDataUpdateCoordinator
from .panel import (
    async_register_panel,
    async_setup_panel_static,
    async_unregister_panel,
)
from .pitboss_api import PitbossApi
from .repairs import async_track_entity_id_rename_issues
from .websocket_api import async_setup as async_setup_websocket_api

type PitbossConfigEntry = ConfigEntry[PitbossDataUpdateCoordinator]

_LOGGER = logging.getLogger(__name__)


async def _async_fetch_device_info(hass: HomeAssistant, host: str) -> dict[str, object]:
    """Fetch normalized Pit Boss device info for a host."""

    api = PitbossApi(host, async_get_clientsession(hass))
    return await api.update_device_info()


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate older Pit Boss config entries to stored metadata and MAC ids."""

    if not (config_entry.version == 1 and config_entry.minor_version < 2):
        return True

    host = config_entry.data[CONF_HOST]
    try:
        device_info = await _async_fetch_device_info(hass, host)
    except (ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning(
            "Unable to migrate Pit Boss entry %s: %s", config_entry.entry_id, err
        )
        return False

    old_unique_id = config_entry.unique_id
    new_unique_id = device_info[INFO_MAC]
    new_data = dict(config_entry.data)
    new_data[DATA_DEVICE_INFO] = device_info

    hass.config_entries.async_update_entry(
        config_entry,
        data=new_data,
        unique_id=new_unique_id,
        minor_version=2,
    )

    device_registry = dr.async_get(hass)
    if old_unique_id and (
        device := device_registry.async_get_device(
            identifiers={(DOMAIN, old_unique_id)}
        )
    ):
        device_registry.async_update_device(
            device.id,
            new_identifiers={(DOMAIN, new_unique_id)},
            new_connections={(dr.CONNECTION_NETWORK_MAC, new_unique_id)},
        )

    entity_registry = er.async_get(hass)
    if old_unique_id and old_unique_id != new_unique_id:
        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        ):
            if not entity_entry.unique_id.startswith(old_unique_id):
                continue

            entity_registry.async_update_entity(
                entity_entry.entity_id,
                new_unique_id=(
                    f"{new_unique_id}{entity_entry.unique_id.removeprefix(old_unique_id)}"
                ),
            )

    return True


async def async_setup_entry(
    hass: HomeAssistant, config_entry: PitbossConfigEntry
) -> bool:
    """Set up Pitboss from a config entry."""

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = True
        async_setup_websocket_api(hass)
        await async_setup_panel_static(hass)

    api = PitbossApi(
        config_entry.data[CONF_HOST],
        async_get_clientsession(hass),
    )
    if device_info := config_entry.data.get(DATA_DEVICE_INFO):
        api.set_device_info(device_info)
    coordinator = PitbossDataUpdateCoordinator(hass, api, config_entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()

    config_entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    await async_register_panel(hass, config_entry)

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    ):
        config_entry.async_on_unload(
            async_track_entity_id_rename_issues(hass, config_entry, device.id)
        )

    config_entry.async_on_unload(
        config_entry.add_update_listener(
            lambda hass, entry: hass.config_entries.async_reload(entry.entry_id)
        )
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: PitbossConfigEntry
) -> bool:
    """Unload a config entry."""

    config_entry.runtime_data.cancel_pending_commands()
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        async_unregister_panel(hass, config_entry)
    return unload_ok
