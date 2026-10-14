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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util.dt import utcnow

from .const import (
    COOK_ANNOTATION_TEXT_FIELDS,
    COOK_CONFIRMATION_WINDOW,
    COOK_DETAIL_STORAGE_VERSION,
    COOK_END_GRACE_PERIOD,
    COOK_SAMPLE_INTERVAL,
    COOK_STORAGE_SAVE_DELAY,
    COOK_STORAGE_VERSION,
    DATA_DEVICE_INFO,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DONE_CONFIRMATION_WINDOW,
    ETA_MAXIMUM,
    ETA_MINIMUM_HISTORY,
    EVENT_DONE_RESET_MARGIN_C,
    EVENT_DONE_RESET_MARGIN_F,
    EVENT_PITBOSS,
    EVENT_STALL_HOLD,
    GRILL_ALERT_DURATION,
    GRILL_ALERT_THRESHOLD_C,
    GRILL_ALERT_THRESHOLD_F,
    INFO_MAC,
    STALL_CONFIRMATION_WINDOW,
    STALL_MINIMUM_TEMPERATURE_C,
    STALL_MINIMUM_TEMPERATURE_F,
    STALL_TREND_THRESHOLD,
    TEMPERATURE_TREND_INTERVAL,
    TEMPERATURE_TREND_WINDOW,
)
from .pitboss_api import PitbossApi, describe_errors, error_codes

_LOGGER = logging.getLogger(__name__)

type CookAnnotations = dict[str, Any]
type CookDetail = dict[str, Any]
type CookError = dict[str, Any]
type CookSample = dict[str, Any]
type CookSession = dict[str, Any]


def _default_cook_annotations() -> CookAnnotations:
    """Return default mutable cook annotations."""

    return {"tags": [], **dict.fromkeys(COOK_ANNOTATION_TEXT_FIELDS)}


def _copy_cook_annotations(annotations: dict[str, Any] | None) -> CookAnnotations:
    """Return a detached copy of cook annotations with every field present."""

    annotations = annotations or {}
    return {
        "tags": list(annotations.get("tags", [])),
        **{field: annotations.get(field) for field in COOK_ANNOTATION_TEXT_FIELDS},
    }


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


def _cook_index_store(hass: HomeAssistant, entry_id: str) -> PitbossCookIndexStore:
    """Return the cook archive index store for a config entry."""

    return PitbossCookIndexStore(
        hass, COOK_STORAGE_VERSION, f"{DOMAIN}_{entry_id}_cook_sessions"
    )


def _cook_detail_store(
    hass: HomeAssistant, entry_id: str, cook_id: str
) -> Store[dict[str, Any]]:
    """Return the sampled-detail store for one completed cook."""

    cook_hash = hashlib.sha1(cook_id.encode(), usedforsecurity=False).hexdigest()
    return Store(
        hass,
        COOK_DETAIL_STORAGE_VERSION,
        f"{DOMAIN}_{entry_id}_cook_detail_{cook_hash}",
    )


async def async_remove_cook_storage(hass: HomeAssistant, entry_id: str) -> None:
    """Delete every cook archive file belonging to a removed config entry."""

    index_store = _cook_index_store(hass, entry_id)
    stored_data = await index_store.async_load() or {}
    for session in stored_data.get("sessions", []):
        await _cook_detail_store(hass, entry_id, session["id"]).async_remove()
    await index_store.async_remove()


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
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_seconds),
        )
        self.api = api
        self._store: Store[dict[str, Any]] = _cook_index_store(
            hass, config_entry.entry_id
        )
        self._cook_detail_stores: dict[str, Store[dict[str, Any]]] = {}
        self._pending_detail_saves: dict[str, CookSession] = {}
        self._store_save_pending = False
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
        # Edge-detection state for pitboss_event notifications.
        # The first poll after start only records state, so a restart doesn't
        # re-announce a probe that is already done or an error already showing.
        self._notifications_primed = False
        # Target a "done" was announced for; latched until the target changes,
        # the probe is unplugged or it drops well below target.
        self._probe_done_notified: dict[str, int | None] = {
            "P1ActTemp": None,
            "P2ActTemp": None,
        }
        self._probe_stall_notified = {"P1ActTemp": False, "P2ActTemp": False}
        self._probe_stall_pending: dict[str, datetime | None] = {
            "P1ActTemp": None,
            "P2ActTemp": None,
        }
        self._notified_error_codes: list[str] = []
        self._probe1_done_restored = False
        # Smoker temperature alert: only armed once the smoker reaches its setpoint.
        self._grill_alert_setpoint: int | None = None
        self._grill_reached_setpoint = False
        self._grill_off_target_since: datetime | None = None
        self._grill_alert_active = False

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
            self._update_notifications(now)
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
            # 0 means the probe is unplugged; a gap must restart the trend.
            if (temperature := int(self.api.get_state_value(key))) <= 0:
                history.clear()
                continue
            history.append((timestamp, temperature))
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

    def get_probe_eta(self, actual_key: str, target_key: str) -> datetime | None:
        """Estimate when a probe reaches its target from its recent trend.

        Returns None when there is no target, the probe is already there, the
        trend is too short to trust, or the probe is stalled or cooling.
        """

        if (target := self.get_probe_target_temperature(target_key)) is None:
            return None

        history = self._temperature_history[actual_key]
        if not history or history[-1][0] - history[0][0] < ETA_MINIMUM_HISTORY:
            return None

        latest_time, latest_temperature = history[-1]
        if (remaining := target - latest_temperature) <= 0:
            return None

        rate = self.get_temperature_change_rate(actual_key)
        if rate is None or rate <= STALL_TREND_THRESHOLD:
            return None

        time_to_target = timedelta(hours=remaining / rate)
        if time_to_target > ETA_MAXIMUM:
            return None
        return (latest_time + time_to_target).replace(second=0, microsecond=0)

    def is_grill_temperature_alert(self) -> bool:
        """Return if the smoker has been far from its setpoint for too long."""

        return self._grill_alert_active

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

    def get_live_snapshot(self) -> dict[str, Any]:
        """Return current readings plus the in-progress cook for the panel."""

        def probe(actual_key: str, target_key: str) -> dict[str, Any]:
            actual = int(self.api.get_state_value(actual_key))
            eta = self.get_probe_eta(actual_key, target_key)
            return {
                "actual": actual if actual > 0 else None,
                "target": self.get_probe_target_temperature(target_key),
                "rate": self.get_temperature_change_rate(actual_key),
                "eta": None if eta is None else eta.isoformat(),
                "stalled": self.is_probe_stalled(actual_key),
                "done": self.is_probe_done(actual_key, target_key),
            }

        error_text = (
            describe_errors(self.api.get_state_value("ErrorStr"))
            if self.api.get_state_value("Error")
            else None
        )
        active_cook = self._active_cook
        return {
            "config_entry_id": self.config_entry.entry_id,
            "online": self.last_update_success,
            "unit": self._get_temperature_unit(),
            "power": bool(self.api.get_state_value("PowerOn")),
            "grill": {
                "actual": int(self.api.get_state_value("GrillActTemp")) or None,
                "target": int(self.api.get_state_value("GrillSetTemp")) or None,
                "rate": self.get_temperature_change_rate("GrillActTemp"),
                "alert": self._grill_alert_active,
            },
            "probe1": probe("P1ActTemp", "P1SetTemp"),
            "probe2": probe("P2ActTemp", "P2SetTemp"),
            "error": error_text or None,
            "cook": (
                None
                if active_cook is None
                else {
                    **self._serialize_cook_session(
                        self._cook_summary_from_active_cook(active_cook),
                        include_config_entry=True,
                    ),
                    "confirmed": active_cook["confirmed_start"] is not None,
                    "samples": [
                        self._serialize_cook_sample(sample)
                        for sample in active_cook.get("samples", [])
                    ],
                    "errors": [
                        self._serialize_cook_error(error)
                        for error in active_cook.get("errors", [])
                    ],
                }
            ),
        }

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
        **details: str | None,
    ) -> dict[str, Any] | None:
        """Update the editable details of a completed or in-progress cook.

        `details` takes the other COOK_ANNOTATION_TEXT_FIELDS (title, food,
        weight, pellets); fields that are not passed are left unchanged.
        """

        if unknown := details.keys() - COOK_ANNOTATION_TEXT_FIELDS.keys():
            raise TypeError(f"Unknown cook annotation fields: {sorted(unknown)}")

        is_active = self._active_cook is not None and self._active_cook["id"] == cook_id
        session = self._active_cook if is_active else self._get_cook_session(cook_id)
        if session is None:
            return None

        if notes is not ...:
            details["notes"] = notes
        annotations = session["annotations"]
        if tags is not None:
            annotations["tags"] = self._normalize_tags(tags)
        for field, value in details.items():
            annotations[field] = self._normalize_text(
                value, COOK_ANNOTATION_TEXT_FIELDS[field]
            )

        self._store_save_pending = False
        await self._store.async_save(self._serialize_store_data())
        if is_active:
            return self._serialize_cook_session(
                self._cook_summary_from_active_cook(session), include_config_entry=True
            )
        return self._serialize_cook_session(session, include_config_entry=True)

    async def async_delete_cook(self, cook_id: str) -> bool:
        """Delete one completed cook and its sampled detail data."""

        if self._get_cook_session(cook_id) is None:
            return False

        self._cook_sessions = [
            session for session in self._cook_sessions if session["id"] != cook_id
        ]

        self._pending_detail_saves.pop(cook_id, None)
        detail_store = self._cook_detail_stores.pop(cook_id, None)
        if detail_store is None:
            detail_store = self._get_cook_detail_store(cook_id)
            self._cook_detail_stores.pop(cook_id, None)

        await detail_store.async_remove()
        self._store_save_pending = False
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
                self._fire_event(
                    "cook_started",
                    cook_id=self._active_cook["id"],
                    start=self._active_cook["start"].isoformat(),
                )

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
            self._fire_event(
                "cook_ended",
                cook_id=completed_cook["id"],
                start=completed_cook["start"].isoformat(),
                end=cook_end.isoformat(),
                duration_minutes=round(completed_cook["duration_seconds"] / 60),
                title=completed_cook["annotations"].get("title"),
            )

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

    def _device_registry_id(self) -> str | None:
        """Return the device registry id of this smoker, if registered."""

        identifier = (
            self.config_entry.data.get(DATA_DEVICE_INFO, {}).get(INFO_MAC)
            or self.config_entry.unique_id
            or self.config_entry.entry_id
        )
        device = dr.async_get(self.hass).async_get_device(
            identifiers={(DOMAIN, identifier)}
        )
        return None if device is None else device.id

    def _fire_event(self, event_type: str, **data: Any) -> None:
        """Fire a pitboss_event on the bus for automations and blueprints."""

        self.hass.bus.async_fire(
            EVENT_PITBOSS,
            {
                "type": event_type,
                "config_entry_id": self.config_entry.entry_id,
                "device_id": self._device_registry_id(),
                "unit": self._get_temperature_unit(),
                **data,
            },
        )

    def _update_notifications(self, timestamp: datetime) -> None:
        """Fire events when probes finish or stall, errors appear, or the fire drifts."""

        primed = self._notifications_primed
        self._notifications_primed = True
        reset_margin = (
            EVENT_DONE_RESET_MARGIN_F
            if self.api.is_fahrenheit()
            else EVENT_DONE_RESET_MARGIN_C
        )

        for probe, actual_key, target_key in (
            (1, "P1ActTemp", "P1SetTemp"),
            (2, "P2ActTemp", "P2SetTemp"),
        ):
            actual = int(self.api.get_state_value(actual_key))
            target = self.get_probe_target_temperature(target_key)
            if (
                not primed
                and actual_key == "P1ActTemp"
                and self._probe1_done_restored
            ):
                self._probe_done_notified[actual_key] = target
            announced_target = self._probe_done_notified[actual_key]
            if announced_target is not None and (
                target != announced_target
                or actual <= 0
                or actual < announced_target - reset_margin
            ):
                announced_target = self._probe_done_notified[actual_key] = None
            if announced_target is None and self.is_probe_done(actual_key, target_key):
                self._probe_done_notified[actual_key] = target
                if primed:
                    self._fire_event(
                        "probe_done", probe=probe, temperature=actual, target=target
                    )

            # The trend wobbles around the stall threshold, so only announce a
            # change that has held for a while.
            stalled = self.is_probe_stalled(actual_key)
            if not primed or stalled == self._probe_stall_notified[actual_key]:
                self._probe_stall_notified[actual_key] = stalled
                self._probe_stall_pending[actual_key] = None
            elif (pending := self._probe_stall_pending[actual_key]) is None:
                self._probe_stall_pending[actual_key] = timestamp
            elif timestamp - pending >= EVENT_STALL_HOLD:
                self._probe_stall_notified[actual_key] = stalled
                self._probe_stall_pending[actual_key] = None
                self._fire_event(
                    "stall_started" if stalled else "stall_ended",
                    probe=probe,
                    temperature=actual,
                )

        codes = (
            error_codes(self.api.get_state_value("ErrorStr"))
            if self.api.get_state_value("Error")
            else []
        )
        if primed and (
            new_codes := [
                code for code in codes if code not in self._notified_error_codes
            ]
        ):
            self._fire_event(
                "error",
                codes=new_codes,
                message=describe_errors(" ".join(new_codes)),
            )
        self._notified_error_codes = codes

        self._update_grill_temperature_alert(timestamp)

    def _update_grill_temperature_alert(self, timestamp: datetime) -> None:
        """Track the smoker drifting away from its setpoint (flameout, empty hopper)."""

        setpoint = int(self.api.get_state_value("GrillSetTemp"))
        actual = int(self.api.get_state_value("GrillActTemp"))
        if not self.api.get_state_value("PowerOn") or setpoint <= 0 or actual <= 0:
            self._grill_alert_setpoint = None
            self._grill_reached_setpoint = False
            self._grill_off_target_since = None
            if self._grill_alert_active:
                self._grill_alert_active = False
                self.async_update_listeners()
            return

        if setpoint != self._grill_alert_setpoint:
            # A new setpoint means a new warm-up or cool-down; re-arm from scratch.
            self._grill_alert_setpoint = setpoint
            self._grill_reached_setpoint = False
            self._grill_off_target_since = None
            if self._grill_alert_active:
                self._grill_alert_active = False
                self.async_update_listeners()

        threshold = (
            GRILL_ALERT_THRESHOLD_F
            if self.api.is_fahrenheit()
            else GRILL_ALERT_THRESHOLD_C
        )
        on_target = abs(actual - setpoint) <= threshold

        if not self._grill_reached_setpoint:
            self._grill_reached_setpoint = on_target
            return

        if on_target:
            self._grill_off_target_since = None
            if self._grill_alert_active:
                self._grill_alert_active = False
                self.async_update_listeners()
                self._fire_event(
                    "grill_temp_recovered", temperature=actual, target=setpoint
                )
            return

        if self._grill_off_target_since is None:
            self._grill_off_target_since = timestamp
        if (
            not self._grill_alert_active
            and timestamp - self._grill_off_target_since >= GRILL_ALERT_DURATION
        ):
            self._grill_alert_active = True
            self.async_update_listeners()
            self._fire_event(
                "grill_temp_alert",
                temperature=actual,
                target=setpoint,
                direction="low" if actual < setpoint else "high",
            )

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

        error_message = describe_errors(self.api.get_state_value("ErrorStr"))
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
            "annotations": _copy_cook_annotations(active_cook["annotations"]),
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
            self._cook_detail_stores[cook_id] = _cook_detail_store(
                self.hass, self.config_entry.entry_id, cook_id
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

        cook_id = active_cook["id"]
        self._pending_detail_saves[cook_id] = active_cook

        def _data_to_save() -> CookDetail:
            # Written now, so unload has nothing left to flush for this cook.
            self._pending_detail_saves.pop(cook_id, None)
            return self._serialize_cook_detail(active_cook)

        self._get_cook_detail_store(cook_id).async_delay_save(
            _data_to_save, COOK_STORAGE_SAVE_DELAY
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
            "GrillActTemp": deque(),
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
            for key, sample_key in (
                ("GrillActTemp", "grill_actual"),
                ("P1ActTemp", "probe1_actual"),
                ("P2ActTemp", "probe2_actual"),
            ):
                if sample[sample_key] <= 0:
                    self._temperature_history[key].clear()
                else:
                    self._temperature_history[key].append(
                        (sample["timestamp"], sample[sample_key])
                    )

        self._previous_probe1_stall = bool(samples[-1].get("probe1_stalled"))
        # Done needs 5 minutes of fresh history, longer than the silent first
        # poll covers, so carry probe 1's recorded done state across restarts.
        # Before the first poll the target reads 0, so latch on the first one seen.
        self._probe1_done_restored = self._active_cook.get("done_at") is not None
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

    def _normalize_text(self, value: str | None | object, max_length: int) -> str | None:
        """Normalize a free-text cook detail for storage."""

        if value is None:
            return None
        cleaned = str(value).strip()[:max_length]
        return cleaned or None

    def _schedule_store_save(self) -> None:
        """Persist cook session state with a small write delay."""

        self._store_save_pending = True
        self._store.async_delay_save(
            self._serialize_store_data, COOK_STORAGE_SAVE_DELAY
        )

    async def async_flush_storage(self) -> None:
        """Write any delayed cook saves now.

        A reload creates a new coordinator that reads the same files. An old
        delayed write landing after that would clobber newer data (for example
        resurrecting a deleted cook), so unload must flush first. async_save
        also cancels the pending delayed write.
        """

        pending_details = self._pending_detail_saves
        self._pending_detail_saves = {}
        for cook_id, cook in pending_details.items():
            await self._get_cook_detail_store(cook_id).async_save(
                self._serialize_cook_detail(cook)
            )

        if self._store_save_pending:
            self._store_save_pending = False
            await self._store.async_save(self._serialize_store_data())

    async def async_shutdown(self) -> None:
        """Cancel polling and flush pending cook data."""

        await super().async_shutdown()
        await self.async_flush_storage()

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
            "annotations": _copy_cook_annotations(session.get("annotations")),
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
            "annotations": _copy_cook_annotations(session.get("annotations")),
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
