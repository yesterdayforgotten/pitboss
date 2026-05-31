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

from custom_components.pitboss.const import DATA_DEVICE_INFO, DOMAIN
from custom_components.pitboss.repairs import build_issue_id
from tests.common import MockConfigEntry
from tests.components.repairs import (
    async_process_repairs_platforms,
    process_repair_fix_flow,
    start_repair_fix_flow,
)
from tests.typing import ClientSessionGenerator


async def _async_setup_entry(
    hass: HomeAssistant,
    title: str = "Pit Boss",
    data: dict[str, object] | None = None,
) -> MockConfigEntry:
    """Set up a Pit Boss config entry for repairs tests."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data=data or {"host": "192.0.2.10"},
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

    issue = issue_registry.async_get_issue(DOMAIN, build_issue_id(device.id, "Porky"))
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
async def test_initial_name_prompt_after_mac_title_creates_fixable_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Updating the initial MAC-based device name should create a repair issue."""

    config_entry = await _async_setup_entry(
        hass,
        title="Pit Boss PBL-0F78550",
        data={
            "host": "192.0.2.10",
            DATA_DEVICE_INFO: {
                "mac": "aa:bb:cc:dd:ee:ff",
                "model_id": "PBL-0F78550",
            },
        },
    )
    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]

    dr.async_get(hass).async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, build_issue_id(device.id, "Porky"))
    assert issue is not None
    assert issue.translation_placeholders == {
        "old_name": "AA:BB:CC:DD:EE:FF",
        "new_name": "Porky",
        "entity_count": "42",
    }
    assert issue.data is not None
    assert "binary_sensor.aa_bb_cc_dd_ee_ff_cook_active" in json.loads(
        issue.data["source_entity_ids"]
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_matching_name_update_does_not_create_repair_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Updating the device name to match the config flow title should not raise a repair."""

    config_entry = await _async_setup_entry(hass, title="Porky")
    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]

    dr.async_get(hass).async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, build_issue_id(device.id, "Porky"))
    assert issue is None


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
        client, DOMAIN, build_issue_id(device.id, "Porky")
    )

    assert result["step_id"] == "init"

    result = await process_repair_fix_flow(client, result["flow_id"])
    assert result["type"] == "menu"

    result = await process_repair_fix_flow(
        client, result["flow_id"], json={"next_step_id": "confirm"}
    )
    assert result["type"] == "form"
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
        DOMAIN, build_issue_id(device.id, "Porky")
    )
    assert first_issue is not None

    device_registry.async_update_device(device.id, name_by_user="Brisket Boss")
    await hass.async_block_till_done()

    updated_issue = issue_registry.async_get_issue(
        DOMAIN, build_issue_id(device.id, "Brisket Boss")
    )
    assert updated_issue is not None
    assert (
        issue_registry.async_get_issue(DOMAIN, build_issue_id(device.id, "Porky"))
        is None
    )
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
async def test_rename_still_finds_default_named_entities_after_missed_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A later rename should still match existing pit_boss ids after a missed earlier repair."""

    config_entry = await _async_setup_entry(hass)
    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]

    device_registry = dr.async_get(hass)
    issue_id = build_issue_id(device.id, "Porky")

    device_registry.async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None

    ir.async_delete_issue(hass, DOMAIN, issue_id)

    device_registry.async_update_device(device.id, name_by_user="Porky2")
    await hass.async_block_till_done()

    updated_issue = issue_registry.async_get_issue(
        DOMAIN, build_issue_id(device.id, "Porky2")
    )
    assert updated_issue is not None
    assert updated_issue.translation_placeholders == {
        "old_name": "Porky",
        "new_name": "Porky2",
        "entity_count": "42",
    }
    assert updated_issue.data is not None
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
        client, DOMAIN, build_issue_id(device.id, "Porky")
    )

    assert result["step_id"] == "init"

    result = await process_repair_fix_flow(client, result["flow_id"])
    assert result["type"] == "menu"

    result = await process_repair_fix_flow(
        client, result["flow_id"], json={"next_step_id": "confirm"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"

    result = await process_repair_fix_flow(client, result["flow_id"])
    assert result["errors"] == {"base": "rename_conflict"}

    assert (
        entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, "PBL-0F78550_cook_active"
        )
        == "binary_sensor.pit_boss_cook_active"
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_rename_fix_flow_ignore_only_applies_to_current_rename(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    hass_client: ClientSessionGenerator,
) -> None:
    """Ignoring one rename should not suppress a later rename issue."""

    config_entry = await _async_setup_entry(hass)
    assert await async_setup_component(hass, "repairs", {})

    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]
    dr.async_get(hass).async_update_device(device.id, name_by_user="Porky")
    await hass.async_block_till_done()

    await async_process_repairs_platforms(hass)
    client = await hass_client()
    first_issue_id = build_issue_id(device.id, "Porky")
    result = await start_repair_fix_flow(client, DOMAIN, first_issue_id)

    assert result["step_id"] == "init"

    result = await process_repair_fix_flow(client, result["flow_id"])
    assert result["type"] == "menu"

    result = await process_repair_fix_flow(
        client, result["flow_id"], json={"next_step_id": "ignore"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "issue_ignored"

    ignored_issue = issue_registry.async_get_issue(DOMAIN, first_issue_id)
    assert ignored_issue is not None
    assert ignored_issue.dismissed_version is not None

    dr.async_get(hass).async_update_device(device.id, name_by_user="Brisket Boss")
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, first_issue_id) is None

    next_issue = issue_registry.async_get_issue(
        DOMAIN, build_issue_id(device.id, "Brisket Boss")
    )
    assert next_issue is not None
    assert next_issue.dismissed_version is None
    assert next_issue.translation_placeholders == {
        "old_name": "Porky",
        "new_name": "Brisket Boss",
        "entity_count": "42",
    }
