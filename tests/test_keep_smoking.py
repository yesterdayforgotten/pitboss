"""Tests for keeping the smoker going when Probe 1 reaches its target."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from tests.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitbossDataUpdateCoordinator
from custom_components.pitboss.number import PitbossProbeTargetNumber
from custom_components.pitboss.switch import PitbossKeepSmokingSwitch


class FakePitbossApi:
    """Fake API that records probe 1 target writes."""

    def __init__(self) -> None:
        """Initialize fake state."""
        self._state: dict[str, int | bool | str] = {
            "P1ActTemp": 150,
            "P2ActTemp": 0,
            "P1SetTemp": 165,
            "GrillSetTemp": 225,
            "GrillActTemp": 225,
            "IsFarenheit": True,
            "PowerOn": True,
            "Error": False,
            "ErrorStr": "",
        }
        self.probe1_writes: list[int] = []
        self.fail_writes = False

    def get_state_value(self, key: str) -> int | bool | str:
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

    async def set_probe1_temp(self, value: float) -> None:
        """Record a probe 1 target write, or fail like an unreachable smoker."""
        if self.fail_writes:
            raise TimeoutError
        self.probe1_writes.append(int(value))
        self._state["P1SetTemp"] = int(value)

    def apply_optimistic_state(self, state: dict) -> None:
        """Apply optimistic state updates."""
        for key, value in state.items():
            if key in self._state:
                self._state[key] = value


@pytest.fixture
def coordinator(hass: HomeAssistant) -> PitbossDataUpdateCoordinator:
    """Return a coordinator backed by the recording fake API."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={},
        unique_id="pitboss-test",
        minor_version=2,
    )
    config_entry.add_to_hass(hass)
    return PitbossDataUpdateCoordinator(hass, FakePitbossApi(), config_entry)


def _switch(hass: HomeAssistant, coordinator) -> PitbossKeepSmokingSwitch:
    entity = PitbossKeepSmokingSwitch(
        coordinator,
        "pitboss-test",
        SwitchEntityDescription(key="keep_smoking", translation_key="keep_smoking"),
    )
    entity.hass = hass
    return entity


def _probe1_number(hass: HomeAssistant, coordinator) -> PitbossProbeTargetNumber:
    entity = PitbossProbeTargetNumber(
        coordinator,
        "pitboss-test",
        NumberEntityDescription(
            key="probe1_target_temp", translation_key="probe1_target_temp"
        ),
    )
    entity.hass = hass
    return entity


async def test_turning_on_adopts_target_and_parks_controller(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """The smoker's target moves into Home Assistant and the controller's is parked."""

    await _switch(hass, coordinator).async_turn_on()

    assert coordinator.keep_smoking
    assert coordinator.api.probe1_writes == [400]
    assert coordinator.get_probe_target_temperature("P1SetTemp") == 165
    assert _probe1_number(hass, coordinator).native_value == 165.0


async def test_target_changes_stay_in_home_assistant(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """While on, setting the Probe 1 target doesn't touch the controller."""

    await _switch(hass, coordinator).async_turn_on()
    await _probe1_number(hass, coordinator).async_set_native_value(203)
    await hass.async_block_till_done()

    assert coordinator.api.probe1_writes == [400]
    assert coordinator.get_probe_target_temperature("P1SetTemp") == 203


async def test_target_set_on_the_smoker_is_adopted_and_reparked(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """A target set from the Pit Boss app becomes the new target and is parked again."""

    await _switch(hass, coordinator).async_turn_on()
    coordinator.api._state["P1SetTemp"] = 190

    await coordinator._async_update_data()

    assert coordinator.get_probe_target_temperature("P1SetTemp") == 190
    assert coordinator.api.probe1_writes == [400, 400]


async def test_parked_target_needs_no_writes(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """Polls leave an already parked or unset controller target alone."""

    await _switch(hass, coordinator).async_turn_on()
    await coordinator._async_update_data()
    coordinator.api._state["P1SetTemp"] = 0
    await coordinator._async_update_data()

    assert coordinator.api.probe1_writes == [400]
    assert coordinator.get_probe_target_temperature("P1SetTemp") == 165


async def test_turning_on_while_offline_parks_on_next_update(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """A failed park keeps the switch on and retries on the next poll."""

    coordinator.api.fail_writes = True
    await _switch(hass, coordinator).async_turn_on()

    assert coordinator.keep_smoking
    assert coordinator.api.probe1_writes == []

    coordinator.api.fail_writes = False
    await coordinator._async_update_data()

    assert coordinator.api.probe1_writes == [400]
    assert coordinator.get_probe_target_temperature("P1SetTemp") == 165


async def test_turning_off_hands_the_target_back(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """Turning off sends the Home Assistant target back to the controller."""

    switch = _switch(hass, coordinator)
    await switch.async_turn_on()
    await _probe1_number(hass, coordinator).async_set_native_value(203)
    await switch.async_turn_off()

    assert not coordinator.keep_smoking
    assert coordinator.api.probe1_writes == [400, 203]
    assert coordinator.get_probe_target_temperature("P1SetTemp") == 203


async def test_turning_off_fails_cleanly_when_offline(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """If the target can't be handed back, the switch stays on."""

    switch = _switch(hass, coordinator)
    await switch.async_turn_on()
    coordinator.api.fail_writes = True

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()

    assert coordinator.keep_smoking


async def test_celsius_parks_at_400_fahrenheit_equivalent(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """In Celsius mode the parked target is 400°F converted and rounded down."""

    coordinator.api._state["IsFarenheit"] = False
    coordinator.api._state["P1SetTemp"] = 74

    await _switch(hass, coordinator).async_turn_on()

    assert coordinator.api.probe1_writes == [204]
    assert coordinator.get_probe_target_temperature("P1SetTemp") == 74


async def test_setting_survives_a_restart(
    hass: HomeAssistant, coordinator: PitbossDataUpdateCoordinator
) -> None:
    """The switch and the Home Assistant target are saved with the cook data."""

    await _switch(hass, coordinator).async_turn_on()
    saved = coordinator._serialize_store_data()

    restarted = PitbossDataUpdateCoordinator(
        hass, FakePitbossApi(), coordinator.config_entry
    )
    restarted._store.async_load = AsyncMock(return_value=saved)
    await restarted.async_initialize()

    assert restarted.keep_smoking
    assert restarted.get_probe_target_temperature("P1SetTemp") == 165
