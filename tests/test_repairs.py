"""Tests for Pit Boss repairs."""

import json
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component

from custom_components.pitboss.const import DOMAIN
from tests.common import MockConfigEntry
from tests.components.repairs import (
    async_process_repairs_platforms,
    process_repair_fix_flow,
    start_repair_fix_flow,
)
from tests.typing import ClientSessionGenerator


async def _async_setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a Pit Boss config entry for repairs tests."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={"host": "192.0.2.10"},
        unique_id="PBL-0F78550",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.pitboss.async_register_panel"),
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_initialize"
        ),
        patch(
            "custom_components.pitboss.coordinator.PitbossDataUpdateCoordinator.async_config_entry_first_refresh"
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)

    await hass.async_block_till_done()
    return config_entry


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_rename_creates_fixable_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test renaming the Pit Boss device creates a fixable issue."""

    config_entry = await _async_setup_entry(hass)
    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]

    dr.async_get(hass).async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, f"rename_entity_ids_{device.id}")
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.translation_key == "rename_entity_ids"
    assert issue.translation_placeholders == {
        "old_name": "Pit Boss",
        "new_name": "Porky",
        "entity_count": "42",
    }
    assert issue.data is not None
    assert "binary_sensor.pit_boss_cook_active" in json.loads(
        issue.data["source_entity_ids"]
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_rename_fix_flow_renames_entity_ids(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test confirming the repair flow renames Pit Boss entity ids."""

    config_entry = await _async_setup_entry(hass)
    assert await async_setup_component(hass, "repairs", {})

    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]
    dr.async_get(hass).async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    await async_process_repairs_platforms(hass)
    client = await hass_client()
    result = await start_repair_fix_flow(
        client, DOMAIN, f"rename_entity_ids_{device.id}"
    )

    assert result["step_id"] == "confirm"

    result = await process_repair_fix_flow(client, result["flow_id"])
    assert result["type"] == "create_entry"

    assert (
        entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, "PBL-0F78550_cook_active"
        )
        == "binary_sensor.porky_cook_active"
    )
    assert (
        entity_registry.async_get_entity_id(
            "sensor", DOMAIN, "PBL-0F78550_current_cook_duration"
        )
        == "sensor.porky_current_cook_duration"
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_second_device_rename_keeps_original_source_ids(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A second rename before repair should preserve the original source ids."""

    config_entry = await _async_setup_entry(hass)
    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]

    device_registry = dr.async_get(hass)
    device_registry.async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    first_issue = issue_registry.async_get_issue(
        DOMAIN, f"rename_entity_ids_{device.id}"
    )
    assert first_issue is not None

    device_registry.async_update_device(device.id, name_by_user="Brisket Boss")
    await hass.async_block_till_done()

    updated_issue = issue_registry.async_get_issue(
        DOMAIN, f"rename_entity_ids_{device.id}"
    )
    assert updated_issue is not None
    assert updated_issue.translation_placeholders == {
        "old_name": "Pit Boss",
        "new_name": "Brisket Boss",
        "entity_count": "42",
    }
    assert updated_issue.data is not None
    assert updated_issue.data["old_name"] == "Pit Boss"
    assert "binary_sensor.pit_boss_cook_active" in json.loads(
        updated_issue.data["source_entity_ids"]
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_rename_fix_flow_reports_entity_id_conflicts(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    hass_client: ClientSessionGenerator,
) -> None:
    """The repair flow should stay open when a target entity id already exists."""

    config_entry = await _async_setup_entry(hass)
    assert await async_setup_component(hass, "repairs", {})

    entity_registry.async_get_or_create(
        "binary_sensor",
        "test_conflict",
        "existing-conflict",
        suggested_object_id="porky_cook_active",
    )

    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]
    dr.async_get(hass).async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    await async_process_repairs_platforms(hass)
    client = await hass_client()
    result = await start_repair_fix_flow(
        client, DOMAIN, f"rename_entity_ids_{device.id}"
    )

    result = await process_repair_fix_flow(client, result["flow_id"])
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"
    assert result["errors"] == {"base": "rename_conflict"}

    assert (
        entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, "PBL-0F78550_cook_active"
        )
        == "binary_sensor.pit_boss_cook_active"
    )
