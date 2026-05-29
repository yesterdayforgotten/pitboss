"""Tests for the Pit Boss cook archive panel lifecycle."""

from unittest.mock import patch

import pytest

from homeassistant.components import frontend
from homeassistant.setup import async_setup_component
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

from custom_components.pitboss import async_setup_entry, async_unload_entry
from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.panel import PANEL_MODULE_URL, get_panel_url_path


async def test_panel_registration_and_unload(hass: HomeAssistant) -> None:
    """Test that one admin-only panel is registered per Pit Boss config entry."""

    assert await async_setup_component(hass, "frontend", {})

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Back Deck",
        data={"host": "192.0.2.10"},
        unique_id="pitboss-back-deck",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_initialize"
        ),
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_config_entry_first_refresh"
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
        ) as mock_forward_entry_setups,
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            return_value=True,
        ) as mock_unload_platforms,
    ):
        assert await async_setup_entry(hass, config_entry)

        panels = hass.data.get(frontend.DATA_PANELS, {})
        panel_url_path = get_panel_url_path(config_entry)
        assert panel_url_path in panels

        panel = panels[panel_url_path]
        assert panel.frontend_url_path == panel_url_path
        assert panel.sidebar_title == "Back Deck Cooks"
        assert panel.config_panel_domain == DOMAIN
        assert panel.require_admin is True
        assert panel.config["config_entry_id"] == config_entry.entry_id
        assert panel.config["title"] == config_entry.title
        assert panel.config["_panel_custom"]["module_url"] == PANEL_MODULE_URL

        mock_forward_entry_setups.assert_called_once()

        assert await async_unload_entry(hass, config_entry)
        assert panel_url_path not in hass.data.get(frontend.DATA_PANELS, {})
        mock_unload_platforms.assert_called_once_with(
            config_entry, mock_forward_entry_setups.call_args.args[1]
        )


async def test_panel_not_registered_when_platform_setup_fails(
    hass: HomeAssistant,
) -> None:
    """Panel registration should not survive a failed platform setup."""

    assert await async_setup_component(hass, "frontend", {})

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Back Deck",
        data={"host": "192.0.2.10"},
        unique_id="pitboss-back-deck",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_initialize"
        ),
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_config_entry_first_refresh"
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            side_effect=RuntimeError("boom"),
        ),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await async_setup_entry(hass, config_entry)

    panel_url_path = get_panel_url_path(config_entry)
    assert panel_url_path not in hass.data.get(frontend.DATA_PANELS, {})


async def test_panel_stays_registered_when_platform_unload_fails(
    hass: HomeAssistant,
) -> None:
    """Panel removal should wait for successful platform unload."""

    assert await async_setup_component(hass, "frontend", {})

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Back Deck",
        data={"host": "192.0.2.10"},
        unique_id="pitboss-back-deck",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_initialize"
        ),
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_config_entry_first_refresh"
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
        ) as mock_forward_entry_setups,
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            return_value=False,
        ),
    ):
        assert await async_setup_entry(hass, config_entry)
        assert await async_unload_entry(hass, config_entry) is False

    panel_url_path = get_panel_url_path(config_entry)
    assert panel_url_path in hass.data.get(frontend.DATA_PANELS, {})
