"""Tests for Pit Boss entity registry naming."""

from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from custom_components.pitboss import async_migrate_entry
from custom_components.pitboss.const import (
    DATA_DEVICE_INFO,
    DOMAIN,
    INFO_FS_FREE,
    INFO_FS_SIZE,
    INFO_FW_VERSION,
    INFO_MAC,
    INFO_MG_ID,
    INFO_MG_VERSION,
    INFO_MODEL_ID,
)
from tests.common import MockConfigEntry


DEVICE_INFO = {
    INFO_MODEL_ID: "PBL-0F78550",
    INFO_MAC: "aa:bb:cc:dd:ee:ff",
    "app": "Lowes",
    INFO_FW_VERSION: "1.2.3",
    "fw_id": "fw-123",
    INFO_MG_VERSION: "2.3.4",
    INFO_MG_ID: "mg-123",
    INFO_FS_SIZE: 8192,
    INFO_FS_FREE: 4096,
    "uptime": 123,
    "ram_size": 4096,
    "ram_free": 2048,
    "ram_min_free": 1024,
    "wifi_sta_ip": "192.0.2.10",
    "wifi_ap_ip": "192.0.2.1",
    "wifi_status": "connected",
    "wifi_ssid": "Backyard",
}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entities_register_with_descriptive_entity_ids(
    hass: HomeAssistant,
) -> None:
    """Test Pit Boss entities get stable descriptive entity ids."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={"host": "192.0.2.10"},
        unique_id="PBL-0F78550",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Living Room")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "PBL-0F78550")},
        manufacturer="Pit Boss",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)

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

    entity_registry = er.async_get(hass)

    assert (
        entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, "PBL-0F78550_cook_active"
        )
        == "binary_sensor.pit_boss_cook_active"
    )
    assert (
        entity_registry.async_get_entity_id(
            "sensor", DOMAIN, "PBL-0F78550_current_cook_duration"
        )
        == "sensor.pit_boss_current_cook_duration"
    )

    assert (
        entity_registry.async_get_entity_id(
            "sensor", DOMAIN, "PBL-0F78550_p1_temp_delta"
        )
        == "sensor.pit_boss_probe_1_delta_to_target"
    )
    assert (
        entity_registry.async_get_entity_id(
            "sensor", DOMAIN, "PBL-0F78550_smoker_temp_rate"
        )
        == "sensor.pit_boss_smoker_temperature_rate"
    )
    assert (
        entity_registry.async_get_entity_id(
            "number", DOMAIN, "PBL-0F78550_probe2_target_temp"
        )
        == "number.pit_boss_probe_2_target_temperature"
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entities_use_configured_device_name_for_initial_ids(
    hass: HomeAssistant,
) -> None:
    """Test the device entry name drives the initial entity ids."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={"host": "192.0.2.10", DATA_DEVICE_INFO: DEVICE_INFO},
        unique_id="aa:bb:cc:dd:ee:ff",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "aa:bb:cc:dd:ee:ff")},
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        manufacturer="Pit Boss",
    )
    device_registry.async_update_device(device.id, name_by_user="Porky")

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

    device = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)[
        0
    ]
    entity_registry = er.async_get(hass)

    assert device.name_by_user == "Porky"
    assert (
        entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, "aa:bb:cc:dd:ee:ff_cook_active"
        )
        == "binary_sensor.porky_cook_active"
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entities_use_device_default_name_for_initial_ids(
    hass: HomeAssistant,
) -> None:
    """Test the device default MAC name drives initial entity ids when no device name exists."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss PBL-0F78550",
        data={"host": "192.0.2.10", DATA_DEVICE_INFO: DEVICE_INFO},
        unique_id="aa:bb:cc:dd:ee:ff",
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

    entity_registry = er.async_get(hass)

    assert (
        entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, "aa:bb:cc:dd:ee:ff_cook_active"
        )
        == "binary_sensor.aa_bb_cc_dd_ee_ff_cook_active"
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_info_projection_and_disabled_diagnostic_sensors(
    hass: HomeAssistant,
) -> None:
    """Project stored info into DeviceInfo and keep info sensors disabled by default."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={"host": "192.0.2.10", DATA_DEVICE_INFO: DEVICE_INFO},
        unique_id="aa:bb:cc:dd:ee:ff",
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

    device = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )[0]
    entity_registry = er.async_get(hass)
    uptime_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "aa:bb:cc:dd:ee:ff_uptime"
    )
    mg_id_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "aa:bb:cc:dd:ee:ff_mg_id"
    )
    fs_free_entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "aa:bb:cc:dd:ee:ff_fs_free"
    )

    assert device.identifiers == {(DOMAIN, "aa:bb:cc:dd:ee:ff")}
    assert device.connections == {(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}
    assert device.name == "AA:BB:CC:DD:EE:FF"
    assert device.model == "PBL-0F78550"
    assert device.model_id == "PBL-0F78550"
    assert device.serial_number == "aa:bb:cc:dd:ee:ff"
    assert device.sw_version == "1.2.3"
    assert device.hw_version == "2.3.4"
    assert device.configuration_url == "http://192.0.2.10"
    assert uptime_entity_id is not None
    assert (
        entity_registry.async_get(uptime_entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    assert mg_id_entity_id is not None
    assert (
        entity_registry.async_get(mg_id_entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    assert fs_free_entity_id is not None
    assert (
        entity_registry.async_get(fs_free_entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_migrate_entry_moves_unique_ids_to_mac(hass: HomeAssistant) -> None:
    """Migrate old model-based identifiers to normalized MAC identifiers."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={"host": "192.0.2.10"},
        unique_id="PBL-0F78550",
        minor_version=1,
    )
    config_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "PBL-0F78550")},
        manufacturer="Pit Boss",
    )

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "PBL-0F78550_cook_active",
        config_entry=config_entry,
        device_id=device.id,
        original_name="Cook Active",
        suggested_object_id="pit_boss_cook_active",
    )

    with patch(
        "custom_components.pitboss._async_fetch_device_info",
        return_value=DEVICE_INFO,
    ):
        assert await async_migrate_entry(hass, config_entry)

    migrated_device = device_registry.async_get(device.id)
    assert config_entry.unique_id == "aa:bb:cc:dd:ee:ff"
    assert config_entry.data[DATA_DEVICE_INFO] == DEVICE_INFO
    assert migrated_device is not None
    assert migrated_device.identifiers == {(DOMAIN, "aa:bb:cc:dd:ee:ff")}
    assert migrated_device.connections == {
        (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")
    }
    assert (
        entity_registry.async_get_entity_id(
            "binary_sensor", DOMAIN, "aa:bb:cc:dd:ee:ff_cook_active"
        )
        == "binary_sensor.pit_boss_cook_active"
    )
