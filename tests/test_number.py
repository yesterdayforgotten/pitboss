"""Tests for the Pit Boss number entities."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.components.number import NumberEntityDescription
from homeassistant.util.dt import utcnow
from homeassistant.util.unit_conversion import TemperatureConverter
from homeassistant.const import UnitOfTemperature

from tests.common import MockConfigEntry, async_fire_time_changed

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitbossDataUpdateCoordinator
from custom_components.pitboss.number import (
    PitbossProbeTargetNumber,
    PitbossVirtualProbeTargetNumber,
)


class FakePitbossApi:
    """Minimal fake API for number entity tests."""

    def __init__(self) -> None:
        """Initialize fake state."""
        self._state: dict[str, int | bool] = {
            "P1ActTemp": 0,
            "P2ActTemp": 0,
            "P1SetTemp": 0,
            "GrillSetTemp": 225,
            "GrillActTemp": 215,
            "IsFarenheit": True,
        }

    def get_state_value(self, key: str) -> int | bool:
        """Return a fake state value."""
        return self._state[key]

    def is_fahrenheit(self) -> bool:
        """Return True if the fake device is in Fahrenheit mode."""
        return bool(self._state["IsFarenheit"])

    async def update_device_info(self) -> dict[str, str]:
        """Pretend to refresh device info."""

        return {}

    def get_device_info_value(self, key: str) -> None:
        """Return one device-info value."""

        return None

    async def set_probe1_temp(self, value: float) -> None:
        """Pretend to write a probe target temperature."""

    def apply_optimistic_state(self, state: dict[str, int]) -> None:
        """Apply optimistic state updates."""

        self._state.update(state)


def _create_coordinator(
    hass: HomeAssistant,
    *,
    is_fahrenheit: bool,
) -> tuple[PitbossDataUpdateCoordinator, str]:
    """Create a coordinator backed by a fake API with the desired unit mode."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={},
        unique_id="pitboss-test",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)

    api = FakePitbossApi()
    api._state["IsFarenheit"] = is_fahrenheit
    return PitbossDataUpdateCoordinator(hass, api, config_entry), config_entry.unique_id


@pytest.mark.parametrize(
    ("is_fahrenheit", "expected_min", "expected_max"),
    [
        pytest.param(True, 130.0, 400.0, id="fahrenheit"),
        pytest.param(
            False,
            TemperatureConverter.convert(
                130,
                UnitOfTemperature.FAHRENHEIT,
                UnitOfTemperature.CELSIUS,
            ),
            TemperatureConverter.convert(
                400,
                UnitOfTemperature.FAHRENHEIT,
                UnitOfTemperature.CELSIUS,
            ),
            id="celsius",
        ),
    ],
)
async def test_probe_target_limits_follow_temperature_mode(
    hass: HomeAssistant,
    is_fahrenheit: bool,
    expected_min: float,
    expected_max: float,
) -> None:
    """Test Probe 1 limits are converted from Fahrenheit in Celsius mode."""
    coordinator, device_id = _create_coordinator(hass, is_fahrenheit=is_fahrenheit)

    entity = PitbossProbeTargetNumber(
        coordinator,
        device_id,
        description=NumberEntityDescription(
            key="probe1_target_temp",
            translation_key="probe1_target_temp",
        ),
    )

    assert entity.native_min_value == expected_min
    assert entity.native_max_value == expected_max


@pytest.mark.parametrize(
    ("is_fahrenheit", "expected_min", "expected_max"),
    [
        pytest.param(True, 130.0, 400.0, id="fahrenheit"),
        pytest.param(
            False,
            TemperatureConverter.convert(
                130,
                UnitOfTemperature.FAHRENHEIT,
                UnitOfTemperature.CELSIUS,
            ),
            TemperatureConverter.convert(
                400,
                UnitOfTemperature.FAHRENHEIT,
                UnitOfTemperature.CELSIUS,
            ),
            id="celsius",
        ),
    ],
)
async def test_virtual_probe_target_limits_follow_temperature_mode(
    hass: HomeAssistant,
    is_fahrenheit: bool,
    expected_min: float,
    expected_max: float,
) -> None:
    """Test Probe 2 limits are converted from Fahrenheit in Celsius mode."""
    coordinator, device_id = _create_coordinator(hass, is_fahrenheit=is_fahrenheit)

    entity = PitbossVirtualProbeTargetNumber(
        coordinator,
        device_id,
        description=NumberEntityDescription(
            key="probe2_target_temp",
            translation_key="probe2_target_temp",
        ),
    )

    assert entity.native_min_value == expected_min
    assert entity.native_max_value == expected_max


async def test_probe_target_step_size_is_ten(
    hass: HomeAssistant,
) -> None:
    """Probe target controls should use a 10-degree step in the UI."""

    coordinator, device_id = _create_coordinator(hass, is_fahrenheit=True)

    probe1_entity = PitbossProbeTargetNumber(
        coordinator,
        device_id,
        description=NumberEntityDescription(
            key="probe1_target_temp",
            translation_key="probe1_target_temp",
        ),
    )
    probe2_entity = PitbossVirtualProbeTargetNumber(
        coordinator,
        device_id,
        description=NumberEntityDescription(
            key="probe2_target_temp",
            translation_key="probe2_target_temp",
        ),
    )

    assert probe1_entity.native_step == 10
    assert probe2_entity.native_step == 10


async def test_probe2_target_number_has_editable_default_value(
    hass: HomeAssistant,
) -> None:
    """Test the virtual Probe 2 target starts with a concrete editable value."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={},
        unique_id="pitboss-test",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)
    coordinator = PitbossDataUpdateCoordinator(hass, FakePitbossApi(), config_entry)

    entity = PitbossVirtualProbeTargetNumber(
        coordinator,
        config_entry.unique_id,
        description=NumberEntityDescription(
            key="probe2_target_temp",
            translation_key="probe2_target_temp",
        ),
    )

    assert entity.available is True
    assert entity.native_value == 0.0
    assert coordinator.get_probe_target_temperature("P2SetTemp") is None

    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_native_value(203.9)

    assert entity.native_value == 203.0
    assert coordinator.get_probe_target_temperature("P2SetTemp") == 203


async def test_successful_command_schedules_awaited_refresh(
    hass: HomeAssistant,
) -> None:
    """A successful command should schedule an awaited delayed refresh."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={},
        unique_id="pitboss-test",
        minor_version=2,
    )
    coordinator = PitbossDataUpdateCoordinator(hass, FakePitbossApi(), config_entry)
    coordinator.async_request_refresh = AsyncMock()

    entity = PitbossProbeTargetNumber(
        coordinator,
        config_entry.unique_id,
        description=NumberEntityDescription(
            key="probe1_target_temp",
            translation_key="probe1_target_temp",
        ),
    )
    entity.hass = hass

    with patch.object(coordinator, "reset_update_interval") as mock_reset:
        entity._handle_successful_command()
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=3))
        await hass.async_block_till_done()

    mock_reset.assert_called_once()
    coordinator.async_request_refresh.assert_awaited_once()
