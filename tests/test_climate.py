"""Tests for the Pit Boss climate entity."""

import pytest

from homeassistant.components.climate import ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription

from tests.common import MockConfigEntry

from custom_components.pitboss.climate import PitbossClimate
from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitbossDataUpdateCoordinator


class FakePitbossApi:
    """Minimal fake API for climate tests."""

    def __init__(self) -> None:
        """Initialize fake state."""
        self._state: dict[str, int | bool] = {
            "PowerOn": False,
            "FanOn": False,
            "IgniterOn": False,
            "Priming": False,
            "GrillActTemp": 0,
            "GrillSetTemp": 225,
            "IsFarenheit": True,
        }

    def get_state_value(self, key: str) -> int | bool:
        """Return a fake state value."""
        return self._state[key]

    def is_fahrenheit(self) -> bool:
        """Return True if the fake device is in Fahrenheit mode."""
        return bool(self._state["IsFarenheit"])

    async def update_state(self) -> None:
        """Pretend to refresh state."""

    async def update_device_info(self) -> dict[str, str]:
        """Pretend to refresh device info."""

        return {}

    def get_device_info_value(self, key: str) -> None:
        """Return one device-info value."""

        return None

    async def set_grill_temp(self, temp: float) -> None:
        """Pretend to set grill temperature."""

    async def set_power_state(self, state: bool) -> None:
        """Pretend to set power state."""

    def apply_optimistic_state(self, state: dict[str, int | bool]) -> None:
        """Apply optimistic state updates."""

        self._state.update(state)


@pytest.fixture
def climate_entity(hass: HomeAssistant) -> PitbossClimate:
    """Return a climate entity backed by a fake API."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={},
        unique_id="pitboss-test",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    coordinator = PitbossDataUpdateCoordinator(hass, FakePitbossApi(), config_entry)
    return PitbossClimate(
        coordinator,
        config_entry.unique_id,
        EntityDescription(
            key="grill_control",
            translation_key="grill_control",
        ),
    )


def test_shutdown_with_fan_reports_fan_action(climate_entity: PitbossClimate) -> None:
    """When power is off but fan is still running, report FAN for cooldown."""
    climate_entity.coordinator.api._state["PowerOn"] = False
    climate_entity.coordinator.api._state["FanOn"] = True

    assert climate_entity.hvac_mode is HVACMode.OFF
    assert climate_entity.hvac_action is HVACAction.FAN


def test_climate_supports_turn_on_and_turn_off(climate_entity: PitbossClimate) -> None:
    """Climate features should advertise explicit turn on and turn off support."""
    assert climate_entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert climate_entity.supported_features & ClimateEntityFeature.TURN_ON
    assert climate_entity.supported_features & ClimateEntityFeature.TURN_OFF
