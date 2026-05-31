"""Data update coordinator for the Pitboss integration."""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import hashlib
import logging
from typing import Any

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util.dt import utcnow

from .const import (
    COOK_CONFIRMATION_WINDOW,
    COOK_DETAIL_STORAGE_VERSION,
    COOK_END_GRACE_PERIOD,
    COOK_SAMPLE_INTERVAL,
    COOK_STORAGE_SAVE_DELAY,
    COOK_STORAGE_VERSION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DONE_CONFIRMATION_WINDOW,
    STALL_CONFIRMATION_WINDOW,
    STALL_MINIMUM_TEMPERATURE_C,
    STALL_MINIMUM_TEMPERATURE_F,
    STALL_TREND_THRESHOLD,
    TEMPERATURE_TREND_INTERVAL,
    TEMPERATURE_TREND_WINDOW,
)
from .pitboss_api import PitbossApi

_LOGGER = logging.getLogger(__name__)

type CookAnnotations = dict[str, Any]
type CookDetail = dict[str, Any]
type CookError = dict[str, Any]
type CookSample = dict[str, Any]
type CookSession = dict[str, Any]


def _default_cook_annotations() -> CookAnnotations:
    """Return default mutable cook annotations."""

    return {"tags": [], "notes": None}


def _default_cook_summary_metrics() -> dict[str, Any]:
    """Return default summary metrics for a cook."""

    return {
        "peak_grill_actual": None,
        "peak_grill_set": None,
        "peak_probe1_actual": None,
        "peak_probe2_actual": None,
        "sample_count": 0,
    }


def _migrate_legacy_cook_session(session: dict[str, Any]) -> CookSession:
    """Convert the original single-store cook schema to the indexed schema."""

    return {
        "id": session["id"],
        "start": session["start"],
        "confirmed_start": session["confirmed_start"],
        "end": session["end"],
        "duration_seconds": session["duration_seconds"],
        "done_at": session["done_at"],
        "stall_count": session["stall_count"],
        "unit": None,
        "summary": _default_cook_summary_metrics(),
        "annotations": _default_cook_annotations(),
    }


class PitbossCookIndexStore(Store[dict[str, Any]]):
    """Store for the Pit Boss cook archive index."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Migrate older cook storage to the indexed format."""

        if old_major_version == 1:
            return {
                "sessions": [
                    _migrate_legacy_cook_session(session)
                    for session in old_data.get("sessions", [])
                ],
                "active_session": (
                    None
                    if (active_session := old_data.get("active_session")) is None
                    else {
                        **_migrate_legacy_cook_session(active_session),
                        "samples": [],
                        "last_sample_bucket": None,
                    }
                ),
            }

        raise NotImplementedError


class PitbossDataUpdateCoordinator(TimestampDataUpdateCoordinator[None]):
    """Class to manage fetching Pitboss data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: PitbossApi,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize Pitboss data update coordinator."""
        interval_seconds = config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_seconds),
        )
        self.api = api
        self.config_entry = config_entry
        self._store: Store[dict[str, Any]] = PitbossCookIndexStore(
            hass,
            COOK_STORAGE_VERSION,
            f"{DOMAIN}_{config_entry.entry_id}_cook_sessions",
        )
        self._cook_detail_stores: dict[str, Store[dict[str, Any]]] = {}
        self._command_lock = asyncio.Lock()
        self._debounced_commands: dict[
            str, tuple[Callable[[], Awaitable[None]], Callable[[], None]]
        ] = {}
        self._pending_command_tasks: set[asyncio.Task[None]] = set()
        self._temperature_history: dict[str, deque[tuple[datetime, int]]] = {
            "GrillActTemp": deque(),
            "P1ActTemp": deque(),
            "P2ActTemp": deque(),
        }
        self._virtual_probe_targets: dict[str, int | None] = {"P2SetTemp": None}
        self._probe_target_reached_at: dict[str, datetime | None] = {
            "P1SetTemp": None,
            "P2SetTemp": None,
        }
        self._cook_sessions: list[CookSession] = []
        self._active_cook: CookSession | None = None
        self._probe1_absent_since: datetime | None = None
        self._previous_probe1_stall = False
        self._active_device_error_message: str | None = None
        self._last_update_error_message: str | None = None

    async def async_initialize(self) -> None:
        """Load persisted cook session data."""

        if (stored_data := await self._store.async_load()) is None:
            return

        self._cook_sessions = [
            self._deserialize_cook_session(session)
            for session in stored_data.get("sessions", [])
        ]
        if active_session := stored_data.get("active_session"):
            self._active_cook = self._deserialize_active_cook(active_session)
            self._probe1_absent_since = (
                None
                if active_session.get("probe1_absent_since") is None
                else datetime.fromisoformat(active_session["probe1_absent_since"])
            )
            self._restore_active_cook_runtime_state()

    async def _async_update_data(self) -> None:
        """Update data via APIs."""
        try:
            await self.api.update_device_info()
            await self.api.update_state()
            self._last_update_error_message = None
            now = utcnow()
            self._record_temperature_history(now)
            self._update_probe_target_reached_times(now)
            self._update_cook_tracking(now)
        except (ClientError, TimeoutError) as ex:
            detail = str(ex) or type(ex).__name__
            message = f"Communication error while updating Pit Boss state: {detail}"
            self._record_cook_error(utcnow(), "update", message)
            raise UpdateFailed(message) from ex
        except ValueError as ex:
            message = f"Received invalid data while updating Pit Boss state: {ex}"
            self._record_cook_error(utcnow(), "update", message)
            raise UpdateFailed(message) from ex

    def reset_update_interval(self) -> None:
        """Restart the polling timer from now.

        Called after a command is issued so the regular 15-second poll never
        fires before the 3-second delayed confirmation refresh.
        """
        self._schedule_refresh()

    async def async_run_serialized_command(
        self, command: Callable[[], Awaitable[None]]
    ) -> None:
        """Run a device command while holding the shared write lock."""

        async with self._command_lock:
            await command()

    def async_schedule_debounced_command(
        self,
        key: str,
        delay: float,
        command: Callable[[], Awaitable[None]],
    ) -> None:
        """Schedule a debounced device command."""

        self.async_cancel_debounced_command(key)

        @callback
        def _run_command(_now) -> None:
            self._debounced_commands.pop(key, None)
            task = self.hass.async_create_task(command())
            self._pending_command_tasks.add(task)
            task.add_done_callback(self._pending_command_tasks.discard)

        self._debounced_commands[key] = (
            command,
            async_call_later(self.hass, delay, _run_command),
        )

    def async_cancel_debounced_command(self, key: str) -> None:
        """Cancel a pending debounced command, if one exists."""

        if pending := self._debounced_commands.pop(key, None):
            pending[1]()

    async def async_flush_debounced_commands(self) -> None:
        """Run queued debounced commands immediately in their current order."""

        pending_commands = list(self._debounced_commands.values())
        self._debounced_commands.clear()

        for command, cancel_callback in pending_commands:
            cancel_callback()
            await command()

    def cancel_pending_commands(self) -> None:
        """Cancel queued debounced commands and in-flight tasks."""

        for key in list(self._debounced_commands):
            self.async_cancel_debounced_command(key)

        for task in list(self._pending_command_tasks):
            task.cancel()

    def is_probe1_present(self) -> bool:
        """Return if Probe 1 appears to be connected."""

        return int(self.api.get_state_value("P1ActTemp")) > 0

    def _record_temperature_history(self, timestamp: datetime) -> None:
        """Record current temperature readings into the rolling history window."""

        cutoff = timestamp - TEMPERATURE_TREND_WINDOW
        for key, history in self._temperature_history.items():
            history.append((timestamp, int(self.api.get_state_value(key))))
            while history and history[0][0] < cutoff:
                history.popleft()

    def get_temperature_change_rate(self, key: str) -> float | None:
        """Return the temperature trend in degrees per hour."""

        history = self._temperature_history[key]
        if len(history) < 2:
            return None

        start_time = history[0][0]
        time_points = [
            (timestamp - start_time).total_seconds() for timestamp, _temp in history
        ]
        temperatures = [temp for _timestamp, temp in history]

        mean_time = sum(time_points) / len(time_points)
        mean_temp = sum(temperatures) / len(temperatures)
        denominator = sum((time_point - mean_time) ** 2 for time_point in time_points)
        if denominator <= 0:
            return None

        numerator = sum(
            (time_point - mean_time) * (temp - mean_temp)
            for time_point, temp in zip(time_points, temperatures, strict=True)
        )
        degrees_per_second = numerator / denominator
        return round(
            degrees_per_second * TEMPERATURE_TREND_INTERVAL.total_seconds(),
            1,
        )

    def set_virtual_probe_target(self, key: str, value: int | None) -> None:
        """Store a local-only probe target and refresh dependent entities."""

        self._virtual_probe_targets[key] = value
        self._update_probe_target_reached_times(utcnow())
        self.async_update_listeners()
        self._schedule_store_save()

    def update_probe_target_reached_times(self) -> None:
        """Recalculate target-reached tracking after an optimistic target change."""

        self._update_probe_target_reached_times(utcnow())
        self.async_update_listeners()
        self._schedule_store_save()

    def get_probe_target_temperature(self, key: str) -> int | None:
        """Return the target temperature for a probe, if one is set."""

        if key == "P1SetTemp":
            value = int(self.api.get_state_value(key))
        else:
            value = self._virtual_probe_targets.get(key)

        if value is None or value <= 0:
            return None
        return value

    def get_probe_temperature_delta(
        self, actual_key: str, target_key: str
    ) -> float | None:
        """Return target minus actual temperature for a probe."""

        if (target := self.get_probe_target_temperature(target_key)) is None:
            return None
        actual = int(self.api.get_state_value(actual_key))
        return float(target - actual)

    def is_probe_stalled(self, actual_key: str) -> bool:
        """Return if a probe appears to have plateaued during a cook."""

        actual = int(self.api.get_state_value(actual_key))
        minimum_temperature = (
            STALL_MINIMUM_TEMPERATURE_F
            if self.api.is_fahrenheit()
            else STALL_MINIMUM_TEMPERATURE_C
        )
        if actual < minimum_temperature:
            return False

        history = self._temperature_history[actual_key]
        if len(history) < 2:
            return False
        if history[-1][0] - history[0][0] < STALL_CONFIRMATION_WINDOW:
            return False

        if (rate := self.get_temperature_change_rate(actual_key)) is None:
            return False
        return abs(rate) <= STALL_TREND_THRESHOLD

    def is_probe_done(self, actual_key: str, target_key: str) -> bool:
        """Return if a probe has stayed at or above target for long enough."""

        if (target := self.get_probe_target_temperature(target_key)) is None:
            return False

        history = self._temperature_history[actual_key]
        if len(history) < 2:
            return False

        cutoff = history[-1][0] - DONE_CONFIRMATION_WINDOW
        if history[0][0] > cutoff:
            return False

        return all(temp >= target for timestamp, temp in history if timestamp >= cutoff)

    def get_time_since_target_reached(self, target_key: str) -> timedelta | None:
        """Return how long the probe has been at or above its target."""

        if (reached_at := self._probe_target_reached_at[target_key]) is None:
            return None
        return utcnow() - reached_at

    def is_cook_active(self) -> bool:
        """Return if a cook session is currently active and confirmed."""

        return (
            self._active_cook is not None
            and self._active_cook["confirmed_start"] is not None
        )

    def get_current_cook_duration(self) -> timedelta | None:
        """Return the current confirmed cook duration."""

        if not self.is_cook_active():
            return None
        return utcnow() - self._active_cook["start"]

    def get_last_cook_duration(self) -> timedelta | None:
        """Return the duration of the most recently completed cook."""

        if not self._cook_sessions:
            return None
        return timedelta(seconds=self._cook_sessions[-1]["duration_seconds"])

    def get_last_cook_start(self) -> datetime | None:
        """Return the start of the most recently completed cook."""

        if not self._cook_sessions:
            return None
        return self._cook_sessions[-1]["start"]

    def get_last_cook_end(self) -> datetime | None:
        """Return the end of the most recently completed cook."""

        if not self._cook_sessions:
            return None
        return self._cook_sessions[-1]["end"]

    def list_cooks(self) -> list[dict[str, Any]]:
        """Return completed cook summaries in reverse chronological order."""

        return [
            self._serialize_cook_session(session, include_config_entry=True)
            for session in reversed(self._cook_sessions)
        ]

    async def async_get_cook(self, cook_id: str) -> dict[str, Any] | None:
        """Return a completed cook with its sampled trace."""

        if (session := self._get_cook_session(cook_id)) is None:
            return None

        detail = await self._async_load_cook_detail(cook_id)
        return {
            **self._serialize_cook_session(session, include_config_entry=True),
            "samples": [
                self._serialize_cook_sample(sample) for sample in detail["samples"]
            ],
            "errors": [self._serialize_cook_error(error) for error in detail["errors"]],
        }

    async def async_update_cook_annotations(
        self,
        cook_id: str,
        *,
        tags: list[str] | None = None,
        notes: str | None | object = None,
    ) -> dict[str, Any] | None:
        """Update the mutable annotations for a completed cook."""

        if (session := self._get_cook_session(cook_id)) is None:
            return None

        if tags is not None:
            session["annotations"]["tags"] = self._normalize_tags(tags)
        if notes is not ...:
            session["annotations"]["notes"] = self._normalize_notes(notes)

        await self._store.async_save(self._serialize_store_data())
        return self._serialize_cook_session(session, include_config_entry=True)

    async def async_delete_cook(self, cook_id: str) -> bool:
        """Delete one completed cook and its sampled detail data."""

        if self._get_cook_session(cook_id) is None:
            return False

        self._cook_sessions = [
            session for session in self._cook_sessions if session["id"] != cook_id
        ]

        detail_store = self._cook_detail_stores.pop(cook_id, None)
        if detail_store is None:
            detail_store = self._get_cook_detail_store(cook_id)
            self._cook_detail_stores.pop(cook_id, None)

        await detail_store.async_remove()
        await self._store.async_save(self._serialize_store_data())
        self.async_update_listeners()
        return True

    def _update_probe_target_reached_times(self, timestamp: datetime) -> None:
        """Update timestamps for when each probe most recently reached target."""

        probe_target_pairs = {
            "P1SetTemp": "P1ActTemp",
            "P2SetTemp": "P2ActTemp",
        }
        for target_key, actual_key in probe_target_pairs.items():
            target = self.get_probe_target_temperature(target_key)
            actual = int(self.api.get_state_value(actual_key))

            if target is None or actual < target:
                self._probe_target_reached_at[target_key] = None
                continue

            if self._probe_target_reached_at[target_key] is None:
                self._probe_target_reached_at[target_key] = timestamp

    def _update_cook_tracking(self, timestamp: datetime) -> None:
        """Track cook sessions based on Probe 1 being connected for at least an hour."""

        probe_present = self.is_probe1_present()
        entity_state_changed = False
        store_state_changed = False

        if probe_present:
            if self._probe1_absent_since is not None:
                self._probe1_absent_since = None
                store_state_changed = True
            if self._active_cook is None:
                self._active_cook = self._create_active_cook(timestamp)
                self._active_device_error_message = None
                self._last_update_error_message = None
                entity_state_changed = True
                store_state_changed = True

            if self._record_active_cook_sample(timestamp):
                store_state_changed = True

            self._sync_device_error_state(timestamp)

            if (
                self._active_cook["confirmed_start"] is None
                and timestamp - self._active_cook["start"] >= COOK_CONFIRMATION_WINDOW
            ):
                self._active_cook["confirmed_start"] = (
                    self._active_cook["start"] + COOK_CONFIRMATION_WINDOW
                )
                entity_state_changed = True
                store_state_changed = True

            if self._active_cook["confirmed_start"] is not None:
                if self._active_cook["done_at"] is None and self.is_probe_done(
                    "P1ActTemp", "P1SetTemp"
                ):
                    self._active_cook["done_at"] = timestamp
                    entity_state_changed = True
                    store_state_changed = True

                stall_now = self.is_probe_stalled("P1ActTemp")
                if stall_now and not self._previous_probe1_stall:
                    self._active_cook["stall_count"] += 1
                    entity_state_changed = True
                    store_state_changed = True
                self._previous_probe1_stall = stall_now
            else:
                self._previous_probe1_stall = False

            if entity_state_changed:
                self.async_update_listeners()
            if store_state_changed:
                self._schedule_store_save()
            return

        self._previous_probe1_stall = False
        if self._active_cook is None:
            return

        if not self.api.get_state_value("Error"):
            self._close_active_device_error(timestamp)

        if self._probe1_absent_since is None:
            self._probe1_absent_since = timestamp
            self._schedule_store_save()
            return

        if timestamp - self._probe1_absent_since < COOK_END_GRACE_PERIOD:
            return

        cook_end = self._probe1_absent_since
        completed_cook = self._active_cook
        if self._active_cook["confirmed_start"] is not None:
            self._close_active_device_error(cook_end)
            self._active_cook["end"] = cook_end
            self._active_cook["duration_seconds"] = int(
                (cook_end - self._active_cook["start"]).total_seconds()
            )
            self._cook_sessions.append(
                self._cook_summary_from_active_cook(self._active_cook)
            )
            self._schedule_cook_detail_save(completed_cook)

        self._active_cook = None
        self._probe1_absent_since = None
        self._active_device_error_message = None
        self._last_update_error_message = None
        self.async_update_listeners()
        self._schedule_store_save()

    def _create_active_cook(self, timestamp: datetime) -> CookSession:
        """Create a new active cook session."""

        return {
            "id": timestamp.isoformat(),
            "start": timestamp,
            "confirmed_start": None,
            "end": None,
            "duration_seconds": None,
            "done_at": None,
            "stall_count": 0,
            "unit": self._get_temperature_unit(),
            "summary": _default_cook_summary_metrics(),
            "annotations": _default_cook_annotations(),
            "errors": [],
            "samples": [],
            "last_sample_bucket": None,
        }

    def _record_active_cook_sample(self, timestamp: datetime) -> bool:
        """Record or replace the current 5-minute sample for the active cook."""

        if self._active_cook is None:
            return False

        sample = self._build_cook_sample(timestamp)
        summary_changed = self._update_active_cook_summary(sample)
        bucket = self._get_sample_bucket(timestamp)
        samples = self._active_cook["samples"]
        sample_changed = False

        if samples and self._active_cook["last_sample_bucket"] == bucket:
            if samples[-1] != sample:
                samples[-1] = sample
                sample_changed = True
        else:
            samples.append(sample)
            self._active_cook["last_sample_bucket"] = bucket
            sample_changed = True

        self._active_cook["summary"]["sample_count"] = len(samples)
        return sample_changed or summary_changed

    def _build_cook_sample(self, timestamp: datetime) -> CookSample:
        """Build the current cook sample from the latest device state."""

        return {
            "timestamp": timestamp,
            "grill_actual": int(self.api.get_state_value("GrillActTemp")),
            "grill_set": int(self.api.get_state_value("GrillSetTemp")),
            "probe1_actual": int(self.api.get_state_value("P1ActTemp")),
            "probe2_actual": int(self.api.get_state_value("P2ActTemp")),
            "probe1_stalled": self.is_probe_stalled("P1ActTemp"),
        }

    def _record_cook_error(
        self, timestamp: datetime, source: str, message: str
    ) -> None:
        """Record one cook-time error event without duplicating consecutive repeats."""

        if self._active_cook is None:
            return

        normalized_message = str(message).strip()
        if not normalized_message:
            return

        if source == "update" and self._last_update_error_message == normalized_message:
            return

        self._active_cook.setdefault("errors", []).append(
            {
                "timestamp": timestamp,
                "source": source,
                "message": normalized_message,
            }
        )
        if source == "update":
            self._last_update_error_message = normalized_message
        self._schedule_store_save()

    def _close_active_device_error(self, timestamp: datetime) -> None:
        """Close the current device error range, if one is open."""

        if self._active_cook is None or self._active_device_error_message is None:
            return

        for error in reversed(self._active_cook.get("errors", [])):
            if (
                error.get("source") == "device"
                and error.get("message") == self._active_device_error_message
                and error.get("end") is None
            ):
                error["end"] = timestamp
                self._schedule_store_save()
                break

        self._active_device_error_message = None

    def _sync_device_error_state(self, timestamp: datetime) -> None:
        """Track device-reported error state changes for the active cook."""

        if self._active_cook is None:
            return

        if not self.api.get_state_value("Error"):
            self._close_active_device_error(timestamp)
            return

        error_message = str(self.api.get_state_value("ErrorStr")).strip()
        if not error_message:
            self._close_active_device_error(timestamp)
            return

        if self._active_device_error_message == error_message:
            return

        self._close_active_device_error(timestamp)
        self._record_cook_error(timestamp, "device", error_message)
        self._active_device_error_message = error_message

    def _update_active_cook_summary(self, sample: CookSample) -> bool:
        """Update peak summary values for the active cook."""

        if self._active_cook is None:
            return False

        changed = False
        summary = self._active_cook["summary"]
        for key, sample_key in (
            ("peak_grill_actual", "grill_actual"),
            ("peak_grill_set", "grill_set"),
            ("peak_probe1_actual", "probe1_actual"),
            ("peak_probe2_actual", "probe2_actual"),
        ):
            value = sample[sample_key]
            if summary[key] is None or value > summary[key]:
                summary[key] = value
                changed = True

        return changed

    def _get_temperature_unit(self) -> str:
        """Return the current pit temperature unit."""

        return "F" if self.api.is_fahrenheit() else "C"

    def _get_sample_bucket(self, timestamp: datetime) -> datetime:
        """Return the 5-minute bucket for a sample timestamp."""

        minutes = int(COOK_SAMPLE_INTERVAL.total_seconds() // 60)
        return timestamp.replace(
            minute=(timestamp.minute // minutes) * minutes,
            second=0,
            microsecond=0,
        )

    def _cook_summary_from_active_cook(self, active_cook: CookSession) -> CookSession:
        """Return the immutable summary stored for a completed cook."""

        return {
            "id": active_cook["id"],
            "start": active_cook["start"],
            "confirmed_start": active_cook["confirmed_start"],
            "end": active_cook["end"],
            "duration_seconds": active_cook["duration_seconds"],
            "done_at": active_cook["done_at"],
            "stall_count": active_cook["stall_count"],
            "unit": active_cook["unit"],
            "summary": dict(active_cook["summary"]),
            "annotations": {
                "tags": list(active_cook["annotations"]["tags"]),
                "notes": active_cook["annotations"]["notes"],
            },
        }

    def _get_cook_session(self, cook_id: str) -> CookSession | None:
        """Return a completed cook session by id."""

        for session in self._cook_sessions:
            if session["id"] == cook_id:
                return session
        return None

    def _get_cook_detail_store(self, cook_id: str) -> Store[dict[str, Any]]:
        """Return the per-cook detail store for a completed cook."""

        if cook_id not in self._cook_detail_stores:
            cook_hash = hashlib.sha1(
                cook_id.encode(), usedforsecurity=False
            ).hexdigest()
            self._cook_detail_stores[cook_id] = Store(
                self.hass,
                COOK_DETAIL_STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_cook_detail_{cook_hash}",
            )

        return self._cook_detail_stores[cook_id]

    async def _async_load_cook_detail(self, cook_id: str) -> CookDetail:
        """Load the detail record for a completed cook."""

        if (
            stored_detail := await self._get_cook_detail_store(cook_id).async_load()
        ) is None:
            return {"id": cook_id, "samples": [], "errors": []}

        return {
            "id": stored_detail["id"],
            "samples": [
                self._deserialize_cook_sample(sample)
                for sample in stored_detail.get("samples", [])
            ],
            "errors": [
                self._deserialize_cook_error(error)
                for error in stored_detail.get("errors", [])
            ],
        }

    def _schedule_cook_detail_save(self, active_cook: CookSession) -> None:
        """Persist sampled detail data for a completed cook."""

        detail_store = self._get_cook_detail_store(active_cook["id"])
        detail_store.async_delay_save(
            lambda: self._serialize_cook_detail(active_cook), COOK_STORAGE_SAVE_DELAY
        )

    def _serialize_cook_detail(self, active_cook: CookSession) -> CookDetail:
        """Serialize the sampled detail data for a completed cook."""

        return {
            "id": active_cook["id"],
            "samples": [
                self._serialize_cook_sample(sample)
                for sample in active_cook.get("samples", [])
            ],
            "errors": [
                self._serialize_cook_error(error)
                for error in active_cook.get("errors", [])
            ],
        }

    def _serialize_cook_sample(self, sample: CookSample) -> dict[str, Any]:
        """Serialize one sampled cook trace point."""

        return {
            **sample,
            "timestamp": sample["timestamp"].isoformat(),
        }

    def _deserialize_cook_sample(self, sample: dict[str, Any]) -> CookSample:
        """Deserialize one sampled cook trace point."""

        deserialized = {
            **sample,
            "timestamp": datetime.fromisoformat(sample["timestamp"]),
        }

        if "probe1_stalled" in sample:
            deserialized["probe1_stalled"] = bool(sample["probe1_stalled"])

        return deserialized

    def _serialize_cook_error(self, error: CookError) -> dict[str, Any]:
        """Serialize one cook-time error entry."""

        serialized = {
            **error,
            "timestamp": error["timestamp"].isoformat(),
        }

        if error.get("end") is not None:
            serialized["end_timestamp"] = error["end"].isoformat()
            serialized.pop("end", None)

        return serialized

    def _deserialize_cook_error(self, error: dict[str, Any]) -> CookError:
        """Deserialize one cook-time error entry."""

        deserialized = {
            **error,
            "timestamp": datetime.fromisoformat(error["timestamp"]),
        }

        if (
            end_timestamp := error.get("end") or error.get("end_timestamp")
        ) is not None:
            deserialized["end"] = datetime.fromisoformat(end_timestamp)

        return deserialized

    def _restore_active_cook_runtime_state(self) -> None:
        """Rebuild transient state for an active cook restored from storage."""

        if self._active_cook is None:
            return

        self._temperature_history = {
            "P1ActTemp": deque(),
            "P2ActTemp": deque(),
        }

        samples = self._active_cook.get("samples", [])
        if not samples:
            self._previous_probe1_stall = False
            self._active_device_error_message = None
            self._last_update_error_message = None
            return

        latest_timestamp = samples[-1]["timestamp"]
        cutoff = latest_timestamp - TEMPERATURE_TREND_WINDOW
        for sample in samples:
            if sample["timestamp"] < cutoff:
                continue
            self._temperature_history["P1ActTemp"].append(
                (sample["timestamp"], sample["probe1_actual"])
            )
            self._temperature_history["P2ActTemp"].append(
                (sample["timestamp"], sample["probe2_actual"])
            )

        self._previous_probe1_stall = bool(samples[-1].get("probe1_stalled"))
        self._active_device_error_message = None
        for error in reversed(self._active_cook.get("errors", [])):
            if error.get("source") == "device" and error.get("end") is None:
                self._active_device_error_message = error["message"]
                break

        self._last_update_error_message = None

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        """Normalize cook tags while preserving user intent."""

        normalized_tags: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            cleaned = tag.strip()
            if not cleaned:
                continue
            cleaned = cleaned.casefold()
            dedupe_key = cleaned
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized_tags.append(cleaned)

        return normalized_tags

    def _normalize_notes(self, notes: str | None | object) -> str | None:
        """Normalize freeform notes for storage."""

        if notes is None:
            return None
        cleaned = str(notes).strip()
        return cleaned or None

    def _schedule_store_save(self) -> None:
        """Persist cook session state with a small write delay."""

        self._store.async_delay_save(
            self._serialize_store_data, COOK_STORAGE_SAVE_DELAY
        )

    def _serialize_store_data(self) -> dict[str, Any]:
        """Return cook session data for storage."""

        return {
            "sessions": [
                self._serialize_cook_session(session) for session in self._cook_sessions
            ],
            "active_session": (
                None
                if self._active_cook is None
                else self._serialize_active_cook(self._active_cook)
            ),
        }

    def _serialize_cook_session(
        self, session: CookSession, *, include_config_entry: bool = False
    ) -> dict[str, Any]:
        """Serialize a cook session for storage."""

        serialized = {
            **session,
            "start": session["start"].isoformat(),
            "confirmed_start": (
                None
                if session["confirmed_start"] is None
                else session["confirmed_start"].isoformat()
            ),
            "end": None if session["end"] is None else session["end"].isoformat(),
            "done_at": (
                None if session["done_at"] is None else session["done_at"].isoformat()
            ),
            "summary": dict(session.get("summary", _default_cook_summary_metrics())),
            "annotations": {
                "tags": list(
                    session.get("annotations", _default_cook_annotations())["tags"]
                ),
                "notes": session.get("annotations", _default_cook_annotations())[
                    "notes"
                ],
            },
            "errors": [
                self._serialize_cook_error(error) for error in session.get("errors", [])
            ],
        }

        if include_config_entry:
            serialized["config_entry_id"] = self.config_entry.entry_id

        return serialized

    def _serialize_active_cook(self, session: CookSession) -> dict[str, Any]:
        """Serialize the active cook including sampled trace data."""

        return {
            **self._serialize_cook_session(session),
            "samples": [
                self._serialize_cook_sample(sample)
                for sample in session.get("samples", [])
            ],
            "probe1_absent_since": (
                None
                if self._probe1_absent_since is None
                else self._probe1_absent_since.isoformat()
            ),
            "last_sample_bucket": (
                None
                if session.get("last_sample_bucket") is None
                else session["last_sample_bucket"].isoformat()
            ),
        }

    def _deserialize_cook_session(self, session: dict[str, Any]) -> CookSession:
        """Deserialize a cook session from storage."""

        return {
            **session,
            "start": datetime.fromisoformat(session["start"]),
            "confirmed_start": (
                None
                if session["confirmed_start"] is None
                else datetime.fromisoformat(session["confirmed_start"])
            ),
            "end": (
                None
                if session["end"] is None
                else datetime.fromisoformat(session["end"])
            ),
            "done_at": (
                None
                if session["done_at"] is None
                else datetime.fromisoformat(session["done_at"])
            ),
            "unit": session.get("unit"),
            "summary": {
                **_default_cook_summary_metrics(),
                **session.get("summary", {}),
            },
            "annotations": {
                "tags": list(session.get("annotations", {}).get("tags", [])),
                "notes": session.get("annotations", {}).get("notes"),
            },
            "errors": [
                self._deserialize_cook_error(error)
                for error in session.get("errors", [])
            ],
        }

    def _deserialize_active_cook(self, session: dict[str, Any]) -> CookSession:
        """Deserialize an active cook session from storage."""

        deserialized = self._deserialize_cook_session(session)
        deserialized["samples"] = [
            self._deserialize_cook_sample(sample)
            for sample in session.get("samples", [])
        ]
        deserialized["last_sample_bucket"] = (
            None
            if session.get("last_sample_bucket") is None
            else datetime.fromisoformat(session["last_sample_bucket"])
        )
        return deserialized
