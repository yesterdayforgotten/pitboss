"""Websocket API for the Pit Boss cook archive."""

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import PitbossDataUpdateCoordinator


@callback
def async_setup(hass: HomeAssistant) -> None:
    """Register the Pit Boss websocket commands."""

    websocket_api.async_register_command(hass, ws_list_cooks)
    websocket_api.async_register_command(hass, ws_get_cook)
    websocket_api.async_register_command(hass, ws_update_cook_annotations)
    websocket_api.async_register_command(hass, ws_delete_cook)


def _get_coordinator(
    hass: HomeAssistant, config_entry_id: str
) -> PitbossDataUpdateCoordinator | None:
    """Return a loaded Pit Boss coordinator by config entry id."""

    if (
        entry := hass.config_entries.async_get_entry(config_entry_id)
    ) is None or entry.domain != DOMAIN:
        return None

    return entry.runtime_data


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pitboss/list_cooks",
        vol.Optional("config_entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_list_cooks(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List completed cooks, optionally filtered by config entry."""

    if config_entry_id := msg.get("config_entry_id"):
        if (coordinator := _get_coordinator(hass, config_entry_id)) is None:
            connection.send_error(
                msg["id"],
                websocket_api.ERR_NOT_FOUND,
                f"Pit Boss config entry {config_entry_id} was not found",
            )
            return

        cooks = coordinator.list_cooks()
    else:
        cooks = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.runtime_data is None:
                continue
            cooks.extend(entry.runtime_data.list_cooks())

        cooks.sort(key=lambda cook: cook["start"], reverse=True)

    connection.send_result(msg["id"], {"cooks": cooks})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pitboss/get_cook",
        vol.Required("config_entry_id"): str,
        vol.Required("cook_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_cook(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return one completed cook with its sampled trace."""

    if (coordinator := _get_coordinator(hass, msg["config_entry_id"])) is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"Pit Boss config entry {msg['config_entry_id']} was not found",
        )
        return

    if (cook := await coordinator.async_get_cook(msg["cook_id"])) is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"Cook {msg['cook_id']} was not found",
        )
        return

    connection.send_result(msg["id"], {"cook": cook})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pitboss/update_cook_annotations",
        vol.Required("config_entry_id"): str,
        vol.Required("cook_id"): str,
        vol.Optional("tags"): [str],
        vol.Optional("notes"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_update_cook_annotations(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update the mutable notes and tags for a completed cook."""

    if (coordinator := _get_coordinator(hass, msg["config_entry_id"])) is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"Pit Boss config entry {msg['config_entry_id']} was not found",
        )
        return

    if not ({"tags", "notes"} & msg.keys()):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_INVALID_FORMAT,
            "At least one of tags or notes must be provided",
        )
        return

    if (
        updated_cook := await coordinator.async_update_cook_annotations(
            msg["cook_id"],
            tags=msg.get("tags"),
            notes=msg["notes"] if "notes" in msg else ...,
        )
    ) is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"Cook {msg['cook_id']} was not found",
        )
        return

    connection.send_result(msg["id"], {"cook": updated_cook})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "pitboss/delete_cook",
        vol.Required("config_entry_id"): str,
        vol.Required("cook_id"): str,
    }
)
@websocket_api.async_response
async def ws_delete_cook(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete one completed cook from the archive."""

    if (coordinator := _get_coordinator(hass, msg["config_entry_id"])) is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"Pit Boss config entry {msg['config_entry_id']} was not found",
        )
        return

    if not await coordinator.async_delete_cook(msg["cook_id"]):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            f"Cook {msg['cook_id']} was not found",
        )
        return

    connection.send_result(msg["id"], {"cook_id": msg["cook_id"]})
