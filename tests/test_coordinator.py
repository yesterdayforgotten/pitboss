"""Tests for the Pitboss coordinator cook-session tracking."""

from collections.abc import Iterable
from datetime import datetime, timedelta
import json
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utcnow

from tests.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.pitboss.const import (
    COOK_CONFIRMATION_WINDOW,
    COOK_END_GRACE_PERIOD,
    DONE_CONFIRMATION_WINDOW,
    DOMAIN,
    EVENT_PITBOSS,
    GRILL_ALERT_DURATION,
    STALL_CONFIRMATION_WINDOW,
    TEMPERATURE_TREND_WINDOW,
)
from custom_components.pitboss.binary_sensor import PitbossCookActiveBinarySensor
from custom_components.pitboss.coordinator import (
    PitbossDataUpdateCoordinator,
    async_remove_cook_storage,
)
from custom_components.pitboss.sensor import (
    PitbossCurrentCookDurationSensor,
    PitbossLastCookDurationSensor,
    PitbossLastCookEndSensor,
    PitbossLastCookStartSensor,
)


class FakePitbossApi:
    """Minimal fake API for coordinator tests."""

    def __init__(self) -> None:
        """Initialize fake state."""
        self._state: dict[str, int | bool] = {
            "P1ActTemp": 0,
            "P2ActTemp": 0,
            "P1SetTemp": 0,
            "GrillSetTemp": 0,
            "GrillActTemp": 0,
            "IsFarenheit": True,
            "PowerOn": False,
            "Error": False,
            "ErrorStr": "",
        }
        self._device_info: dict[str, int | str] = {"fw_version": "1.2.3"}

    def get_state_value(self, key: str) -> int | bool:
        """Return a fake state value."""
        return self._state[key]

    def is_fahrenheit(self) -> bool:
        """Return True if the fake device is in Fahrenheit mode."""
        return bool(self._state["IsFarenheit"])

    async def update_state(self) -> None:
        """Pretend to refresh state."""

    async def update_device_info(self) -> dict[str, int | str]:
        """Pretend to refresh device info."""

        return self._device_info

    def get_device_info_value(self, key: str) -> int | str | None:
        """Return one device-info value."""

        return self._device_info.get(key)


@pytest.fixture
def coordinator(hass: HomeAssistant) -> PitbossDataUpdateCoordinator:
    """Return a coordinator backed by a fake API."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={},
        unique_id="pitboss-test",
        minor_version=2,
    )
    return PitbossDataUpdateCoordinator(hass, FakePitbossApi(), config_entry)


async def test_update_data_refreshes_device_info(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Refreshing data should also refresh cached device info."""

    await coordinator._async_update_data()

    assert coordinator.api.get_device_info_value("fw_version") == "1.2.3"


def test_grill_temperature_rate_is_tracked(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """The coordinator should calculate a smoker/grill temperature trend."""

    start = utcnow()
    coordinator.api._state["GrillActTemp"] = 200
    coordinator._record_temperature_history(start)

    coordinator.api._state["GrillActTemp"] = 210
    coordinator._record_temperature_history(start + TEMPERATURE_TREND_WINDOW)

    assert coordinator.get_temperature_change_rate("GrillActTemp") == 20.0


async def test_debounced_command_runs_on_event_loop(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A debounced command should run from the event loop timer callback."""

    command: AsyncMock = AsyncMock()

    coordinator.async_schedule_debounced_command("test", 5, command)

    async_fire_time_changed(hass, utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()

    command.assert_awaited_once()


def _confirm_cook(coordinator: PitbossDataUpdateCoordinator, start: datetime) -> None:
    """Start and confirm a cook session."""
    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(start)
    coordinator._update_cook_tracking(start + COOK_CONFIRMATION_WINDOW)


def _record_probe1_history(
    coordinator: PitbossDataUpdateCoordinator,
    start: datetime,
    entries: Iterable[tuple[timedelta, int]],
) -> None:
    """Record Probe 1 temperature history for derived-state checks."""
    for offset, temperature in entries:
        coordinator.api._state["P1ActTemp"] = temperature
        coordinator._record_temperature_history(start + offset)


def _complete_confirmed_cook(
    coordinator: PitbossDataUpdateCoordinator, start: datetime
) -> datetime:
    """Confirm and end a cook session."""
    _confirm_cook(coordinator, start)
    probe_removed_at = start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)
    return probe_removed_at


def test_current_cook_duration_starts_at_probe_insertion(
    coordinator: PitbossDataUpdateCoordinator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The active cook duration should measure from initial probe insertion."""
    start = utcnow()

    freezer.move_to(start)
    _confirm_cook(coordinator, start)
    freezer.move_to(start + COOK_CONFIRMATION_WINDOW)

    assert coordinator.is_cook_active() is True
    assert coordinator.get_current_cook_duration() == COOK_CONFIRMATION_WINDOW


def test_unconfirmed_cook_is_not_saved(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A short probe insertion should not create a completed cook session."""
    start = utcnow()

    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(start)

    probe_removed_at = start + timedelta(minutes=30)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)

    assert coordinator.is_cook_active() is False
    assert coordinator.get_last_cook_start() is None
    assert coordinator.get_last_cook_end() is None
    assert coordinator.get_last_cook_duration() is None


def test_confirmed_cook_is_saved_after_probe_absent_grace_period(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A confirmed cook should complete when Probe 1 stays absent past grace period."""
    start = utcnow()

    _confirm_cook(coordinator, start)

    probe_removed_at = start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)

    assert coordinator.is_cook_active() is False
    assert coordinator.get_last_cook_start() == start
    assert coordinator.get_last_cook_end() == probe_removed_at
    assert coordinator.get_last_cook_duration() == COOK_CONFIRMATION_WINDOW + timedelta(
        minutes=10
    )


def test_reconnect_within_grace_period_keeps_current_cook(
    coordinator: PitbossDataUpdateCoordinator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A brief probe disconnect should not end the active cook."""
    start = utcnow()

    _confirm_cook(coordinator, start)

    probe_removed_at = start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)

    reconnected_at = probe_removed_at + COOK_END_GRACE_PERIOD - timedelta(minutes=1)
    freezer.move_to(reconnected_at)
    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(reconnected_at)

    assert coordinator.is_cook_active() is True
    assert coordinator.get_last_cook_start() is None
    assert coordinator.get_current_cook_duration() == reconnected_at - start


def test_probe_absent_beyond_grace_period_ends_current_cook(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A disconnect longer than the grace period should end the current cook."""
    start = utcnow()

    _confirm_cook(coordinator, start)

    probe_removed_at = start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)

    assert coordinator.is_cook_active() is False
    assert coordinator.get_last_cook_start() == start
    assert coordinator.get_last_cook_end() == probe_removed_at


def test_done_timestamp_is_recorded_after_done_window(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A confirmed cook should record when Probe 1 is done."""
    start = utcnow()
    coordinator.api._state["P1SetTemp"] = 160
    _confirm_cook(coordinator, start)

    done_at = start + COOK_CONFIRMATION_WINDOW + DONE_CONFIRMATION_WINDOW
    _record_probe1_history(
        coordinator,
        start + COOK_CONFIRMATION_WINDOW,
        (
            (timedelta(0), 165),
            (DONE_CONFIRMATION_WINDOW / 2, 165),
            (DONE_CONFIRMATION_WINDOW, 165),
        ),
    )
    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(done_at)

    assert coordinator._active_cook is not None
    assert coordinator._active_cook["done_at"] == done_at


def test_stall_count_only_increments_on_new_stall_periods(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Repeated stalled updates should count once per distinct stall episode."""
    start = utcnow()
    _confirm_cook(coordinator, start)

    stall_start = start + COOK_CONFIRMATION_WINDOW
    _record_probe1_history(
        coordinator,
        stall_start,
        (
            (timedelta(0), 165),
            (STALL_CONFIRMATION_WINDOW / 2, 165),
            (STALL_CONFIRMATION_WINDOW, 165),
        ),
    )
    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(stall_start + STALL_CONFIRMATION_WINDOW)

    assert coordinator._active_cook is not None
    assert coordinator._active_cook["stall_count"] == 1

    coordinator._update_cook_tracking(
        stall_start + STALL_CONFIRMATION_WINDOW + timedelta(minutes=1)
    )
    assert coordinator._active_cook["stall_count"] == 1

    _record_probe1_history(
        coordinator,
        stall_start,
        ((STALL_CONFIRMATION_WINDOW + timedelta(minutes=2), 175),),
    )
    coordinator.api._state["P1ActTemp"] = 175
    coordinator._update_cook_tracking(
        stall_start + STALL_CONFIRMATION_WINDOW + timedelta(minutes=2)
    )

    _record_probe1_history(
        coordinator,
        stall_start,
        (
            (STALL_CONFIRMATION_WINDOW + timedelta(minutes=22), 175),
            (STALL_CONFIRMATION_WINDOW + timedelta(minutes=32), 175),
            (STALL_CONFIRMATION_WINDOW + timedelta(minutes=42), 175),
        ),
    )
    coordinator._update_cook_tracking(
        stall_start + STALL_CONFIRMATION_WINDOW + timedelta(minutes=42)
    )

    assert coordinator._active_cook["stall_count"] == 2


async def test_async_initialize_restores_sessions_and_active_cook(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Stored cook sessions should be restored on coordinator initialization."""
    start = utcnow()
    confirmed_start = start + COOK_CONFIRMATION_WINDOW
    end = confirmed_start + timedelta(minutes=10)

    coordinator._store.async_load = AsyncMock(
        return_value={
            "sessions": [
                {
                    "id": "completed",
                    "start": start.isoformat(),
                    "confirmed_start": confirmed_start.isoformat(),
                    "end": end.isoformat(),
                    "duration_seconds": int((end - start).total_seconds()),
                    "done_at": None,
                    "stall_count": 1,
                }
            ],
            "active_session": {
                "id": "active",
                "start": end.isoformat(),
                "confirmed_start": None,
                "end": None,
                "duration_seconds": None,
                "done_at": None,
                "stall_count": 0,
                "summary": {"sample_count": 0},
                "annotations": {"tags": [], "notes": None},
                "samples": [],
                "last_sample_bucket": None,
            },
        }
    )

    await coordinator.async_initialize()

    assert coordinator.get_last_cook_start() == start
    assert coordinator.get_last_cook_end() == end
    assert coordinator.get_last_cook_duration() == end - start
    assert coordinator._active_cook is not None
    assert coordinator._active_cook["id"] == "active"
    assert coordinator._active_cook["start"] == end


async def test_async_initialize_restores_active_cook_runtime_history(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Restoring an active cook should rebuild stall tracking state."""

    start = utcnow().replace(minute=0, second=0, microsecond=0)
    stalled_at = start + COOK_CONFIRMATION_WINDOW + STALL_CONFIRMATION_WINDOW
    coordinator.api._state["P1ActTemp"] = 165

    coordinator._store.async_load = AsyncMock(
        return_value={
            "sessions": [],
            "active_session": {
                "id": "active",
                "start": start.isoformat(),
                "confirmed_start": (start + COOK_CONFIRMATION_WINDOW).isoformat(),
                "end": None,
                "duration_seconds": None,
                "done_at": None,
                "stall_count": 1,
                "summary": {"sample_count": 3},
                "annotations": {"tags": [], "notes": None},
                "errors": [],
                "samples": [
                    {
                        "timestamp": (
                            stalled_at - STALL_CONFIRMATION_WINDOW
                        ).isoformat(),
                        "grill_actual": 225,
                        "grill_set": 250,
                        "probe1_actual": 165,
                        "probe2_actual": 90,
                        "probe1_stalled": True,
                    },
                    {
                        "timestamp": (
                            stalled_at - STALL_CONFIRMATION_WINDOW / 2
                        ).isoformat(),
                        "grill_actual": 225,
                        "grill_set": 250,
                        "probe1_actual": 165,
                        "probe2_actual": 90,
                        "probe1_stalled": True,
                    },
                    {
                        "timestamp": stalled_at.isoformat(),
                        "grill_actual": 225,
                        "grill_set": 250,
                        "probe1_actual": 165,
                        "probe2_actual": 90,
                        "probe1_stalled": True,
                    },
                ],
                "last_sample_bucket": stalled_at.isoformat(),
            },
        }
    )

    await coordinator.async_initialize()

    assert coordinator._previous_probe1_stall is True
    assert coordinator.is_probe_stalled("P1ActTemp") is True
    assert len(coordinator._temperature_history["GrillActTemp"]) == 3
    assert coordinator.get_temperature_change_rate("GrillActTemp") == 0.0


async def test_async_initialize_restores_open_device_error_range(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Restoring an active cook should keep an open device error resumable."""

    start = utcnow().replace(minute=0, second=0, microsecond=0)
    coordinator._store.async_load = AsyncMock(
        return_value={
            "sessions": [],
            "active_session": {
                "id": "active",
                "start": start.isoformat(),
                "confirmed_start": (start + COOK_CONFIRMATION_WINDOW).isoformat(),
                "end": None,
                "duration_seconds": None,
                "done_at": None,
                "stall_count": 0,
                "summary": {"sample_count": 1},
                "annotations": {"tags": [], "notes": None},
                "errors": [
                    {
                        "timestamp": start.isoformat(),
                        "source": "device",
                        "message": "NoPellets",
                    }
                ],
                "samples": [
                    {
                        "timestamp": start.isoformat(),
                        "grill_actual": 225,
                        "grill_set": 250,
                        "probe1_actual": 165,
                        "probe2_actual": 90,
                        "probe1_stalled": False,
                    }
                ],
                "last_sample_bucket": start.isoformat(),
            },
        }
    )

    await coordinator.async_initialize()

    assert coordinator._active_device_error_message == "NoPellets"


async def test_async_initialize_restores_probe_absent_grace_window(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Restoring an active cook should preserve the existing probe-absent grace window."""

    start = utcnow().replace(minute=0, second=0, microsecond=0)
    absent_since = start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0

    coordinator._store.async_load = AsyncMock(
        return_value={
            "sessions": [],
            "active_session": {
                "id": "active",
                "start": start.isoformat(),
                "confirmed_start": (start + COOK_CONFIRMATION_WINDOW).isoformat(),
                "end": None,
                "duration_seconds": None,
                "done_at": None,
                "stall_count": 0,
                "summary": {"sample_count": 1},
                "annotations": {"tags": [], "notes": None},
                "errors": [],
                "samples": [
                    {
                        "timestamp": absent_since.isoformat(),
                        "grill_actual": 225,
                        "grill_set": 250,
                        "probe1_actual": 165,
                        "probe2_actual": 90,
                        "probe1_stalled": False,
                    }
                ],
                "probe1_absent_since": absent_since.isoformat(),
                "last_sample_bucket": absent_since.isoformat(),
            },
        }
    )

    await coordinator.async_initialize()

    assert coordinator._probe1_absent_since == absent_since

    coordinator._update_cook_tracking(absent_since + COOK_END_GRACE_PERIOD)

    assert coordinator.is_cook_active() is False
    assert coordinator.get_last_cook_end() == absent_since


def test_cook_samples_are_downsampled_to_five_minute_buckets(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Cook traces should keep one latest sample per 5-minute bucket."""
    start = utcnow().replace(minute=0, second=0, microsecond=0)

    coordinator.api._state.update(
        {
            "P1ActTemp": 120,
            "P2ActTemp": 90,
            "GrillSetTemp": 250,
            "GrillActTemp": 230,
        }
    )
    coordinator._update_cook_tracking(start)

    coordinator.api._state.update(
        {
            "P1ActTemp": 125,
            "P2ActTemp": 95,
            "GrillActTemp": 235,
        }
    )
    coordinator._update_cook_tracking(start + timedelta(minutes=2))

    coordinator.api._state.update(
        {
            "P1ActTemp": 130,
            "P2ActTemp": 100,
            "GrillActTemp": 240,
        }
    )
    coordinator._update_cook_tracking(start + timedelta(minutes=5))

    assert coordinator._active_cook is not None
    assert len(coordinator._active_cook["samples"]) == 2
    assert coordinator._active_cook["samples"][0]["probe1_actual"] == 125
    assert coordinator._active_cook["samples"][0]["grill_actual"] == 235
    assert coordinator._active_cook["samples"][1]["probe1_actual"] == 130
    assert coordinator._active_cook["summary"]["sample_count"] == 2
    assert coordinator._active_cook["summary"]["peak_grill_actual"] == 240
    assert coordinator._active_cook["summary"]["peak_grill_set"] == 250


async def test_update_cook_annotations_only_changes_mutable_fields(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Completed cooks should only allow notes and tags to change."""
    start = utcnow()
    _complete_confirmed_cook(coordinator, start)

    updated = await coordinator.async_update_cook_annotations(
        start.isoformat(),
        tags=[" brisket ", "overnight", "Brisket"],
        notes=" wrapped at 165F ",
    )

    assert updated is not None
    assert updated["annotations"] == {
        "tags": ["brisket", "overnight"],
        "title": None,
        "food": None,
        "weight": None,
        "pellets": None,
        "notes": "wrapped at 165F",
    }
    assert updated["start"] == start.isoformat()


async def test_async_get_cook_returns_saved_stall_samples_and_errors(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Completed cook detail should include stall-state samples and error events."""

    start = utcnow().replace(minute=0, second=0, microsecond=0)
    _confirm_cook(coordinator, start)

    stall_start = start + COOK_CONFIRMATION_WINDOW
    _record_probe1_history(
        coordinator,
        stall_start,
        (
            (timedelta(0), 165),
            (STALL_CONFIRMATION_WINDOW / 2, 165),
            (STALL_CONFIRMATION_WINDOW, 165),
        ),
    )
    coordinator.api._state["P1ActTemp"] = 165
    coordinator.api._state["Error"] = True
    coordinator.api._state["ErrorStr"] = "NoPellets"
    coordinator._update_cook_tracking(stall_start + STALL_CONFIRMATION_WINDOW)

    probe_removed_at = stall_start + STALL_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator.api._state["Error"] = False
    coordinator.api._state["ErrorStr"] = ""
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)

    cook = await coordinator.async_get_cook(start.isoformat())

    assert cook is not None
    assert any(sample["probe1_stalled"] for sample in cook["samples"])
    assert cook["errors"] == [
        {
            "timestamp": (stall_start + STALL_CONFIRMATION_WINDOW).isoformat(),
            "source": "device",
            "message": "Out of pellets",
            "end_timestamp": probe_removed_at.isoformat(),
        }
    ]


async def test_device_error_range_closes_without_duplicate_when_update_error_occurs(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A continuous device fault should stay one ranged error despite update errors."""

    start = utcnow().replace(minute=0, second=0, microsecond=0)
    _confirm_cook(coordinator, start)

    device_error_at = start + COOK_CONFIRMATION_WINDOW
    coordinator.api._state["Error"] = True
    coordinator.api._state["ErrorStr"] = "NoPellets"
    coordinator._update_cook_tracking(device_error_at)

    coordinator._record_cook_error(
        device_error_at + timedelta(minutes=5),
        "update",
        "Communication error while updating Pit Boss state: boom",
    )
    coordinator._update_cook_tracking(device_error_at + timedelta(minutes=10))

    probe_removed_at = device_error_at + timedelta(minutes=15)
    coordinator.api._state["Error"] = False
    coordinator.api._state["ErrorStr"] = ""
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)

    cook = await coordinator.async_get_cook(start.isoformat())

    assert cook is not None
    assert cook["errors"] == [
        {
            "timestamp": device_error_at.isoformat(),
            "source": "device",
            "message": "Out of pellets",
            "end_timestamp": probe_removed_at.isoformat(),
        },
        {
            "timestamp": (device_error_at + timedelta(minutes=5)).isoformat(),
            "source": "update",
            "message": "Communication error while updating Pit Boss state: boom",
        },
    ]


def test_current_cook_duration_sensor_tracks_confirmed_cook(
    coordinator: PitbossDataUpdateCoordinator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The current cook duration sensor should reflect the active confirmed cook."""
    sensor = PitbossCurrentCookDurationSensor(coordinator, "pitboss-test")
    start = utcnow()

    assert sensor.available is False
    assert sensor.native_value is None

    freezer.move_to(start)
    _confirm_cook(coordinator, start)
    freezer.move_to(start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=5))

    assert sensor.available is True
    assert sensor.native_value == 65.0


def test_last_cook_summary_sensors_reflect_completed_cook(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """The last cook summary sensors should expose the most recent completed cook."""
    duration_sensor = PitbossLastCookDurationSensor(coordinator, "pitboss-test")
    start_sensor = PitbossLastCookStartSensor(coordinator, "pitboss-test")
    end_sensor = PitbossLastCookEndSensor(coordinator, "pitboss-test")
    start = utcnow()

    assert duration_sensor.available is False
    assert duration_sensor.native_value is None
    assert start_sensor.available is False
    assert start_sensor.native_value is None
    assert end_sensor.available is False
    assert end_sensor.native_value is None

    probe_removed_at = _complete_confirmed_cook(coordinator, start)

    assert duration_sensor.available is True
    assert duration_sensor.native_value == 70.0
    assert start_sensor.available is True
    assert start_sensor.native_value == start
    assert end_sensor.available is True
    assert end_sensor.native_value == probe_removed_at


def test_cook_active_binary_sensor_reflects_confirmation_and_completion(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """The cook active binary sensor should only turn on for confirmed cooks."""
    sensor = PitbossCookActiveBinarySensor(coordinator, "pitboss-test")
    start = utcnow()

    assert sensor.is_on is False

    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(start)
    assert sensor.is_on is False

    coordinator._update_cook_tracking(start + COOK_CONFIRMATION_WINDOW)
    assert sensor.is_on is True

    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(
        start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    )
    coordinator._update_cook_tracking(
        start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10) + COOK_END_GRACE_PERIOD
    )

    assert sensor.is_on is False


def test_unplugged_probe_resets_temperature_history(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A 0 reading means unplugged and must not be treated as a temperature."""

    start = utcnow()
    coordinator.api._state["P1ActTemp"] = 150
    coordinator._record_temperature_history(start)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._record_temperature_history(start + timedelta(minutes=1))

    assert len(coordinator._temperature_history["P1ActTemp"]) == 0
    assert coordinator.get_temperature_change_rate("P1ActTemp") is None


async def test_shutdown_flushes_delayed_cook_saves(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Unloading must write pending data so a reload never reads stale files."""

    coordinator._store.async_save = AsyncMock()
    coordinator._schedule_store_save()

    await coordinator.async_shutdown()

    coordinator._store.async_save.assert_awaited_once()
    coordinator._store.async_save.reset_mock()
    await coordinator.async_flush_storage()
    coordinator._store.async_save.assert_not_awaited()


async def test_remove_cook_storage_deletes_index_and_details(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Removing an entry deletes the archive index and every cook detail file."""

    entry_id = coordinator.config_entry.entry_id
    await coordinator._store.async_save(
        {"sessions": [{"id": "cook-1"}], "active_session": None}
    )
    detail_store = coordinator._get_cook_detail_store("cook-1")
    await detail_store.async_save({"id": "cook-1", "samples": [], "errors": []})

    await async_remove_cook_storage(hass, entry_id)

    assert await coordinator._store.async_load() is None
    assert await detail_store.async_load() is None


def test_probe_eta_extrapolates_recent_trend(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """The ETA extends the recent rate of rise to the probe target."""

    start = utcnow().replace(second=0, microsecond=0)
    coordinator.api._state["P1SetTemp"] = 200
    _record_probe1_history(
        coordinator, start, [(timedelta(0), 150), (timedelta(minutes=15), 160)]
    )

    # 40 degrees/hour with 40 degrees to go.
    assert coordinator.get_probe_eta("P1ActTemp", "P1SetTemp") == start + timedelta(
        minutes=75
    )


@pytest.mark.parametrize(
    ("target", "entries"),
    [
        (0, [(timedelta(0), 150), (timedelta(minutes=15), 160)]),
        (200, [(timedelta(0), 150), (timedelta(minutes=5), 155)]),
        (200, [(timedelta(0), 160), (timedelta(minutes=20), 160)]),
        (200, [(timedelta(0), 195), (timedelta(minutes=15), 201)]),
    ],
    ids=["no-target", "short-history", "stalled", "already-there"],
)
def test_probe_eta_is_unknown_when_it_cannot_be_estimated(
    coordinator: PitbossDataUpdateCoordinator,
    target: int,
    entries: list[tuple[timedelta, int]],
) -> None:
    """No ETA without a target, enough history, or a rising temperature."""

    coordinator.api._state["P1SetTemp"] = target
    _record_probe1_history(coordinator, utcnow(), entries)

    assert coordinator.get_probe_eta("P1ActTemp", "P1SetTemp") is None


async def test_probe_done_event_fires_once(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A probe reaching its target is announced once, not on every poll."""

    events = async_capture_events(hass, EVENT_PITBOSS)
    start = utcnow()
    coordinator._update_notifications(start)  # first poll only records state
    coordinator.api._state["P1SetTemp"] = 200
    _record_probe1_history(
        coordinator,
        start,
        [(timedelta(0), 201), (DONE_CONFIRMATION_WINDOW, 202)],
    )

    coordinator._update_notifications(start + DONE_CONFIRMATION_WINDOW)
    coordinator._update_notifications(
        start + DONE_CONFIRMATION_WINDOW + timedelta(minutes=1)
    )
    await hass.async_block_till_done()

    assert [event.data["type"] for event in events] == ["probe_done"]
    assert events[0].data["probe"] == 1
    assert events[0].data["temperature"] == 202
    assert events[0].data["target"] == 200
    assert events[0].data["unit"] == "F"
    assert events[0].data["config_entry_id"] == coordinator.config_entry.entry_id


async def test_error_event_fires_for_each_new_error(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Each newly raised controller error is announced in plain language."""

    events = async_capture_events(hass, EVENT_PITBOSS)
    start = utcnow()
    coordinator._update_notifications(start - timedelta(minutes=1))
    coordinator.api._state["Error"] = True
    coordinator.api._state["ErrorStr"] = "NoPellets"
    coordinator._update_notifications(start)
    coordinator._update_notifications(start + timedelta(minutes=1))
    coordinator.api._state["ErrorStr"] = "NoPellets FanErr"
    coordinator._update_notifications(start + timedelta(minutes=2))
    await hass.async_block_till_done()

    assert [(event.data["codes"], event.data["message"]) for event in events] == [
        (["NoPellets"], "Out of pellets"),
        (["FanErr"], "Combustion fan fault"),
    ]


async def test_grill_temperature_alert_needs_setpoint_reached_first(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Warm-up never alerts; a sustained drop after reaching setpoint does."""

    events = async_capture_events(hass, EVENT_PITBOSS)
    state = coordinator.api._state
    start = utcnow()
    state.update(PowerOn=True, GrillSetTemp=225, GrillActTemp=100)

    coordinator._update_notifications(start)
    coordinator._update_notifications(start + GRILL_ALERT_DURATION * 3)
    assert coordinator.is_grill_temperature_alert() is False

    state["GrillActTemp"] = 220
    coordinator._update_notifications(start + timedelta(hours=1))

    dropped_at = start + timedelta(hours=2)
    state["GrillActTemp"] = 180
    coordinator._update_notifications(dropped_at)
    coordinator._update_notifications(
        dropped_at + GRILL_ALERT_DURATION - timedelta(seconds=1)
    )
    assert coordinator.is_grill_temperature_alert() is False

    coordinator._update_notifications(dropped_at + GRILL_ALERT_DURATION)
    assert coordinator.is_grill_temperature_alert() is True

    state["GrillActTemp"] = 222
    coordinator._update_notifications(
        dropped_at + GRILL_ALERT_DURATION + timedelta(minutes=1)
    )
    assert coordinator.is_grill_temperature_alert() is False
    await hass.async_block_till_done()

    assert [event.data["type"] for event in events] == [
        "grill_temp_alert",
        "grill_temp_recovered",
    ]
    assert events[0].data["direction"] == "low"
    assert events[0].data["temperature"] == 180
    assert events[0].data["target"] == 225


def test_grill_temperature_alert_rearms_on_new_setpoint(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Changing the setpoint clears the alert and waits for the new target."""

    state = coordinator.api._state
    start = utcnow()
    state.update(PowerOn=True, GrillSetTemp=225, GrillActTemp=225)
    coordinator._update_notifications(start)
    state["GrillActTemp"] = 150
    coordinator._update_notifications(start + timedelta(minutes=1))
    coordinator._update_notifications(start + timedelta(minutes=1) + GRILL_ALERT_DURATION)
    assert coordinator.is_grill_temperature_alert() is True

    state["GrillSetTemp"] = 300
    coordinator._update_notifications(start + timedelta(hours=1))
    coordinator._update_notifications(start + timedelta(hours=2))
    assert coordinator.is_grill_temperature_alert() is False


async def test_active_cook_details_carry_into_the_archive(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Details entered while cooking are kept when the cook is archived."""

    start = utcnow()
    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(start)

    updated = await coordinator.async_update_cook_annotations(
        start.isoformat(),
        title=" Saturday brisket ",
        food="Brisket",
        weight="x" * 100,
        notes=...,
    )

    assert updated is not None
    assert updated["annotations"]["title"] == "Saturday brisket"
    assert updated["annotations"]["food"] == "Brisket"
    assert updated["annotations"]["weight"] == "x" * 40
    assert updated["annotations"]["pellets"] is None

    coordinator._update_cook_tracking(start + COOK_CONFIRMATION_WINDOW)
    probe_removed_at = start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)

    assert coordinator.list_cooks()[0]["annotations"]["title"] == "Saturday brisket"


async def test_update_cook_annotations_rejects_unknown_fields(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Only the known detail fields can be written."""

    start = utcnow()
    _complete_confirmed_cook(coordinator, start)

    with pytest.raises(TypeError):
        await coordinator.async_update_cook_annotations(
            start.isoformat(), colour="red"
        )


def test_live_snapshot_reports_readings_and_active_cook(
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """The panel's live feed carries readings plus the in-progress cook."""

    start = utcnow()
    coordinator.api._state.update(
        PowerOn=True, GrillSetTemp=225, GrillActTemp=220, P1ActTemp=165
    )
    coordinator._update_cook_tracking(start)

    snapshot = coordinator.get_live_snapshot()

    json.dumps(snapshot)
    assert snapshot["power"] is True
    assert snapshot["grill"] == {
        "actual": 220,
        "target": 225,
        "rate": None,
        "alert": False,
    }
    assert snapshot["probe1"]["actual"] == 165
    assert snapshot["probe2"]["actual"] is None
    assert snapshot["error"] is None
    assert snapshot["cook"]["id"] == start.isoformat()
    assert snapshot["cook"]["confirmed"] is False
    assert len(snapshot["cook"]["samples"]) == 1


async def test_probe_done_event_latches_until_probe_drops_well_below_target(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """Wobbling around target during a rest must not re-announce done."""

    events = async_capture_events(hass, EVENT_PITBOSS)
    start = utcnow()
    coordinator._update_notifications(start)
    coordinator.api._state["P1SetTemp"] = 200

    readings = [201, 202, 199, 201, 202, 203, 201]
    for minute, temperature in enumerate(readings):
        _record_probe1_history(
            coordinator, start, [(timedelta(minutes=minute * 5), temperature)]
        )
        coordinator._update_notifications(start + timedelta(minutes=minute * 5))
    await hass.async_block_till_done()
    assert [event.data["type"] for event in events] == ["probe_done"]

    # Pulled and re-probed (well below target): the next done is announced.
    later = start + timedelta(hours=1)
    _record_probe1_history(coordinator, later, [(timedelta(0), 150)])
    coordinator._update_notifications(later)
    _record_probe1_history(
        coordinator,
        later,
        [(timedelta(minutes=30), 200), (timedelta(minutes=35), 201)],
    )
    coordinator._update_notifications(later + timedelta(minutes=35))
    await hass.async_block_till_done()
    assert [event.data["type"] for event in events] == ["probe_done", "probe_done"]


async def test_stall_events_need_the_change_to_hold(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A stall flag flickering at the threshold is not announced."""

    events = async_capture_events(hass, EVENT_PITBOSS)
    start = utcnow()
    stalled = {"value": False}
    coordinator.is_probe_stalled = lambda key: key == "P1ActTemp" and stalled["value"]
    coordinator._update_notifications(start)

    stalled["value"] = True
    coordinator._update_notifications(start + timedelta(minutes=1))
    stalled["value"] = False
    coordinator._update_notifications(start + timedelta(minutes=2))
    stalled["value"] = True
    coordinator._update_notifications(start + timedelta(minutes=3))
    coordinator._update_notifications(start + timedelta(minutes=7))
    await hass.async_block_till_done()
    assert events == []

    coordinator._update_notifications(start + timedelta(minutes=8))
    await hass.async_block_till_done()
    assert [(event.data["type"], event.data["probe"]) for event in events] == [
        ("stall_started", 1)
    ]


async def test_first_poll_after_start_is_silent(
    hass: HomeAssistant,
    coordinator: PitbossDataUpdateCoordinator,
) -> None:
    """A restart must not re-announce an error that is already showing."""

    events = async_capture_events(hass, EVENT_PITBOSS)
    start = utcnow()
    coordinator.api._state["Error"] = True
    coordinator.api._state["ErrorStr"] = "NoPellets"

    coordinator._update_notifications(start)
    coordinator._update_notifications(start + timedelta(minutes=1))
    await hass.async_block_till_done()

    assert events == []
