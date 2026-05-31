"""Tests for the Pit Boss config flow."""

from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pitboss.const import DATA_DEVICE_INFO, DOMAIN
from custom_components.pitboss.config_flow import CONF_SUBNET, UnsupportedModel


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow_manual_entry(hass: HomeAssistant) -> None:
    """Test the Pit Boss user flow exposes manual entry and stores device info."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert "manual" in result["menu_options"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "manual"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert {key.schema for key in result["data_schema"].schema} == {CONF_HOST}

    device_info = {"model_id": "PBL-0F78550", "mac": "AA:BB:CC:DD:EE:FF"}

    with (
        patch(
            "custom_components.pitboss.config_flow._async_validate_input",
            return_value=device_info,
        ),
        patch("custom_components.pitboss.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "192.0.2.10"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Pit Boss PBL-0F78550"
    assert result["data"] == {CONF_HOST: "192.0.2.10", DATA_DEVICE_INFO: device_info}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow_discovery_selection(hass: HomeAssistant) -> None:
    """Test discovery flow lists supported smokers and stores chosen metadata."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    with patch(
        "custom_components.pitboss.config_flow._async_discover_supported_devices",
        return_value={
            "192.0.2.10": {
                "model_id": "PBL-0F78550",
                "mac": "AA:BB:CC:DD:EE:FF",
                "app": "Lowes",
            }
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"next_step_id": "discover"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discover"
    assert {key.schema for key in result["data_schema"].schema} == {CONF_HOST}

    selector = result["data_schema"].schema[next(iter(result["data_schema"].schema))]
    assert selector.config["options"] == [
        {
            "value": "192.0.2.10",
            "label": "PBL-0F78550 | AA:BB:CC:DD:EE:FF | Lowes",
        }
    ]

    with patch("custom_components.pitboss.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "192.0.2.10"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Pit Boss PBL-0F78550"
    assert result["data"] == {
        CONF_HOST: "192.0.2.10",
        DATA_DEVICE_INFO: {
            "model_id": "PBL-0F78550",
            "mac": "AA:BB:CC:DD:EE:FF",
            "app": "Lowes",
        },
    }


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow_discovery_falls_back_to_custom_subnet(
    hass: HomeAssistant,
) -> None:
    """Test discovery falls back to explicit subnet scan when auto-detection finds nothing."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    with patch(
        "custom_components.pitboss.config_flow._async_discover_supported_devices",
        side_effect=[
            {},
            {
                "192.0.2.10": {
                    "model_id": "PBL-0F78550",
                    "mac": "AA:BB:CC:DD:EE:FF",
                    "app": "Lowes",
                }
            },
        ],
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"next_step_id": "discover"},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "discover_subnet"
        assert {key.schema for key in result["data_schema"].schema} == {CONF_SUBNET}
        subnet_key = next(iter(result["data_schema"].schema))
        assert subnet_key.default() == "192.168.0.0/24"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_SUBNET: "192.0.2.0/24"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discover"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow_discovery_rejects_invalid_custom_subnet(
    hass: HomeAssistant,
) -> None:
    """Test explicit subnet fallback validates the subnet input."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    with patch(
        "custom_components.pitboss.config_flow._async_discover_supported_devices",
        return_value={},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"next_step_id": "discover"},
        )

    assert result["step_id"] == "discover_subnet"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_SUBNET: "not-a-subnet"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discover_subnet"
    assert result["errors"] == {"base": "invalid_subnet"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow_rejects_unsupported_model(hass: HomeAssistant) -> None:
    """Unsupported smoker models should fail validation."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "manual"},
    )

    with patch(
        "custom_components.pitboss.config_flow._async_validate_input",
        side_effect=UnsupportedModel("PBL-12345678"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_HOST: "192.0.2.10"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unsupported_model"}
    assert result["description_placeholders"] == {"model": "PBL-12345678"}
