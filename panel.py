"""Custom panel registration for the Pit Boss cook archive."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

PANEL_STATIC_URL = "/pitboss_static"
PANEL_MODULE_NAME = "pitboss-cook-panel"
PANEL_MODULE_URL = f"{PANEL_STATIC_URL}/pitboss-panel.js"


def _panel_asset_path() -> str:
    """Return the path containing the panel frontend assets."""

    return str(Path(__file__).parent / "panel")


@callback
def get_panel_url_path(config_entry: ConfigEntry) -> str:
    """Return the frontend URL path for a Pit Boss config entry panel."""

    return f"{DOMAIN}-{config_entry.entry_id}"


@callback
def get_panel_sidebar_title(config_entry: ConfigEntry) -> str:
    """Return the sidebar title for a Pit Boss config entry panel."""

    return f"{config_entry.title} Cooks"


async def async_setup_panel_static(hass: HomeAssistant) -> None:
    """Register static panel assets once for the Pit Boss integration."""

    if hass.http is None:
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_URL, _panel_asset_path(), cache_headers=False)]
    )


async def async_register_panel(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Register the cook archive panel for one Pit Boss config entry."""

    frontend_url_path = get_panel_url_path(config_entry)
    if frontend.async_panel_exists(hass, frontend_url_path):
        frontend.async_remove_panel(hass, frontend_url_path, warn_if_unknown=False)

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=frontend_url_path,
        sidebar_title=get_panel_sidebar_title(config_entry),
        sidebar_icon="mdi:grill-outline",
        config_panel_domain=DOMAIN,
        webcomponent_name=PANEL_MODULE_NAME,
        module_url=PANEL_MODULE_URL,
        embed_iframe=False,
        require_admin=True,
        config={
            "config_entry_id": config_entry.entry_id,
            "title": config_entry.title,
        },
    )


@callback
def async_unregister_panel(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Remove the cook archive panel for one Pit Boss config entry."""

    frontend.async_remove_panel(
        hass, get_panel_url_path(config_entry), warn_if_unknown=False
    )
