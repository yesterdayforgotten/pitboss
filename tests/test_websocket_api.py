"""Tests for the Pitboss websocket cook archive API."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from homeassistant.components.websocket_api import const as websocket_api_const
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util.dt import utcnow

from tests.common import MockConfigEntry, MockUser
from tests.typing import WebSocketGenerator

from custom_components.pitboss.const import (
    COOK_CONFIRMATION_WINDOW,
    COOK_END_GRACE_PERIOD,
    DOMAIN,
    STALL_CONFIRMATION_WINDOW,
)
from custom_components.pitboss.coordinator import PitbossDataUpdateCoordinator
from custom_components.pitboss.websocket_api import (
    async_setup as async_setup_websocket_api,
)


class FakePitbossApi:
    """Minimal fake API for websocket tests."""

    def __init__(self) -> None:
        """Initialize fake state."""
        self._state: dict[str, int | bool] = {
            "P1ActTemp": 0,
            "P2ActTemp": 0,
            "P1SetTemp": 0,
            "GrillSetTemp": 225,
            "GrillActTemp": 215,
            "IsFarenheit": True,
            "PowerOn": False,
            "Error": False,
            "ErrorStr": "",
        }

    async def update_state(self) -> None:
        """Pretend to refresh state."""

    async def update_device_info(self) -> dict[str, str]:
        """Pretend to refresh device info."""

        return {}

    def get_state_value(self, key: str) -> int | bool:
        """Return a fake state value."""
        return self._state[key]

    def is_fahrenheit(self) -> bool:
        """Return True if the fake device is in Fahrenheit mode."""
        return bool(self._state["IsFarenheit"])

    def get_device_info_value(self, key: str) -> None:
        """Return one cached device-info value."""

        return None


def _create_coordinator(
    hass: HomeAssistant,
) -> tuple[MockConfigEntry, PitbossDataUpdateCoordinator]:
    """Create a config entry and coordinator for websocket tests."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss",
        data={},
        unique_id="pitboss-test",
        minor_version=2,
        state=ConfigEntryState.LOADED,
    )
    config_entry.add_to_hass(hass)
    coordinator = PitbossDataUpdateCoordinator(hass, FakePitbossApi(), config_entry)
    config_entry.runtime_data = coordinator
    return config_entry, coordinator


def _complete_confirmed_cook(
    coordinator: PitbossDataUpdateCoordinator, start: datetime
) -> str:
    """Create one completed cook with a sampled trace."""
    coordinator.api._state["P1ActTemp"] = 150
    coordinator._update_cook_tracking(start)
    coordinator.api._state["P1ActTemp"] = 165
    coordinator.api._state["P2ActTemp"] = 95
    coordinator._update_cook_tracking(start + timedelta(minutes=2))
    coordinator._update_cook_tracking(start + COOK_CONFIRMATION_WINDOW)

    probe_removed_at = start + COOK_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)
    return start.isoformat()


async def test_list_cooks(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test listing archived cooks."""
    config_entry, coordinator = _create_coordinator(hass)
    cook_id = _complete_confirmed_cook(
        coordinator, utcnow().replace(minute=0, second=0, microsecond=0)
    )
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": "pitboss/list_cooks",
            "config_entry_id": config_entry.entry_id,
        }
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert len(msg["result"]["cooks"]) == 1
    assert msg["result"]["cooks"][0]["id"] == cook_id
    assert msg["result"]["cooks"][0]["config_entry_id"] == config_entry.entry_id


async def test_archive_read_commands_require_admin(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: MockUser,
) -> None:
    """Read-only cook archive websocket commands should require admin."""

    config_entry, coordinator = _create_coordinator(hass)
    cook_id = _complete_confirmed_cook(
        coordinator, utcnow().replace(minute=0, second=0, microsecond=0)
    )
    async_setup_websocket_api(hass)

    hass_admin_user.groups = []
    client = await hass_ws_client(hass)

    await client.send_json(
        {
            "id": 10,
            "type": "pitboss/list_cooks",
            "config_entry_id": config_entry.entry_id,
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == websocket_api_const.ERR_UNAUTHORIZED

    await client.send_json(
        {
            "id": 11,
            "type": "pitboss/get_cook",
            "config_entry_id": config_entry.entry_id,
            "cook_id": cook_id,
        }
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == websocket_api_const.ERR_UNAUTHORIZED


async def test_get_cook(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test fetching one archived cook with its trace samples."""
    config_entry, coordinator = _create_coordinator(hass)
    cook_id = _complete_confirmed_cook(
        coordinator, utcnow().replace(minute=0, second=0, microsecond=0)
    )
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 2,
            "type": "pitboss/get_cook",
            "config_entry_id": config_entry.entry_id,
            "cook_id": cook_id,
        }
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["cook"]["id"] == cook_id
    assert len(msg["result"]["cook"]["samples"]) == 2
    assert msg["result"]["cook"]["summary"]["sample_count"] == 2
    assert msg["result"]["cook"]["samples"][0]["probe1_stalled"] is False
    assert msg["result"]["cook"]["errors"] == []


async def test_update_cook_annotations(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test updating mutable cook annotations over websocket."""
    config_entry, coordinator = _create_coordinator(hass)
    cook_id = _complete_confirmed_cook(
        coordinator, utcnow().replace(minute=0, second=0, microsecond=0)
    )
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 3,
            "type": "pitboss/update_cook_annotations",
            "config_entry_id": config_entry.entry_id,
            "cook_id": cook_id,
            "tags": ["brisket", "overnight"],
            "notes": "wrapped at 165F",
        }
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["cook"]["annotations"] == {
        "tags": ["brisket", "overnight"],
        "title": None,
        "food": None,
        "weight": None,
        "pellets": None,
        "notes": "wrapped at 165F",
    }


async def test_delete_cook(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test deleting one archived cook over websocket."""

    config_entry, coordinator = _create_coordinator(hass)
    cook_id = _complete_confirmed_cook(
        coordinator, utcnow().replace(minute=0, second=0, microsecond=0)
    )
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 4,
            "type": "pitboss/delete_cook",
            "config_entry_id": config_entry.entry_id,
            "cook_id": cook_id,
        }
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"] == {"cook_id": cook_id}
    assert coordinator.list_cooks() == []

    await client.send_json(
        {
            "id": 5,
            "type": "pitboss/get_cook",
            "config_entry_id": config_entry.entry_id,
            "cook_id": cook_id,
        }
    )
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_get_cook_includes_recorded_device_and_update_errors(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test archived cook details include saved error events and stall samples."""

    config_entry, coordinator = _create_coordinator(hass)
    start = utcnow().replace(minute=0, second=0, microsecond=0)
    _complete_confirmed_cook(coordinator, start)
    coordinator._cook_sessions.clear()
    coordinator._active_cook = None

    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(start)
    coordinator._update_cook_tracking(start + COOK_CONFIRMATION_WINDOW)

    stall_start = start + COOK_CONFIRMATION_WINDOW
    for offset in (
        timedelta(0),
        STALL_CONFIRMATION_WINDOW / 2,
        STALL_CONFIRMATION_WINDOW,
    ):
        coordinator.api._state["P1ActTemp"] = 165
        coordinator._record_temperature_history(stall_start + offset)

    coordinator.api._state["Error"] = True
    coordinator.api._state["ErrorStr"] = "NoPellets"
    coordinator._update_cook_tracking(stall_start + STALL_CONFIRMATION_WINDOW)

    coordinator.api.update_state = AsyncMock(side_effect=TimeoutError("boom"))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    probe_removed_at = stall_start + STALL_CONFIRMATION_WINDOW + timedelta(minutes=10)
    coordinator.api._state["Error"] = False
    coordinator.api._state["ErrorStr"] = ""
    coordinator.api._state["P1ActTemp"] = 0
    coordinator._update_cook_tracking(probe_removed_at)
    coordinator._update_cook_tracking(probe_removed_at + COOK_END_GRACE_PERIOD)

    async_setup_websocket_api(hass)
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 6,
            "type": "pitboss/get_cook",
            "config_entry_id": config_entry.entry_id,
            "cook_id": start.isoformat(),
        }
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert any(sample["probe1_stalled"] for sample in msg["result"]["cook"]["samples"])
    assert msg["result"]["cook"]["errors"] == [
        {
            "timestamp": (stall_start + STALL_CONFIRMATION_WINDOW).isoformat(),
            "source": "device",
            "message": "Out of pellets",
            "end_timestamp": probe_removed_at.isoformat(),
        },
        {
            "timestamp": msg["result"]["cook"]["errors"][1]["timestamp"],
            "source": "update",
            "message": "Communication error while updating Pit Boss state: boom",
        },
    ]


async def test_list_cooks_skips_entries_that_are_not_loaded(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """An entry stuck in setup retry has no runtime_data and must be skipped."""
    config_entry, coordinator = _create_coordinator(hass)
    _complete_confirmed_cook(
        coordinator, utcnow().replace(minute=0, second=0, microsecond=0)
    )
    retrying_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pit Boss 2",
        data={},
        unique_id="pitboss-retrying",
        minor_version=2,
        state=ConfigEntryState.SETUP_RETRY,
    )
    retrying_entry.add_to_hass(hass)
    async_setup_websocket_api(hass)
    client = await hass_ws_client(hass)

    await client.send_json({"id": 1, "type": "pitboss/list_cooks"})
    response = await client.receive_json()
    assert response["success"]
    assert len(response["result"]["cooks"]) == 1

    await client.send_json(
        {
            "id": 2,
            "type": "pitboss/list_cooks",
            "config_entry_id": retrying_entry.entry_id,
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == websocket_api_const.ERR_NOT_FOUND


async def test_update_cook_details(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Title, food, weight and pellets can be set without touching notes."""
    config_entry, coordinator = _create_coordinator(hass)
    cook_id = _complete_confirmed_cook(
        coordinator, utcnow().replace(minute=0, second=0, microsecond=0)
    )
    await coordinator.async_update_cook_annotations(cook_id, notes="keep me")
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 9,
            "type": "pitboss/update_cook_annotations",
            "config_entry_id": config_entry.entry_id,
            "cook_id": cook_id,
            "title": "Christmas brisket",
            "food": "Brisket",
            "weight": "14 lb",
            "pellets": None,
        }
    )
    msg = await client.receive_json()

    assert msg["success"]
    assert msg["result"]["cook"]["annotations"] == {
        "tags": [],
        "title": "Christmas brisket",
        "food": "Brisket",
        "weight": "14 lb",
        "pellets": None,
        "notes": "keep me",
    }


async def test_subscribe_live_streams_snapshots(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """The live subscription sends a snapshot now and after each update."""
    config_entry, coordinator = _create_coordinator(hass)
    coordinator.api._state["P1ActTemp"] = 165
    coordinator._update_cook_tracking(utcnow())
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 7,
            "type": "pitboss/subscribe_live",
            "config_entry_id": config_entry.entry_id,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]

    msg = await client.receive_json()
    assert msg["type"] == "event"
    assert msg["event"]["config_entry_id"] == config_entry.entry_id
    assert msg["event"]["cook"]["confirmed"] is False
    assert msg["event"]["probe1"]["actual"] == 165

    coordinator.api._state["P1ActTemp"] = 170
    coordinator.async_update_listeners()
    msg = await client.receive_json()
    assert msg["event"]["probe1"]["actual"] == 170

    await client.send_json(
        {"id": 8, "type": "unsubscribe_events", "subscription": 7}
    )
    msg = await client.receive_json()
    assert msg["success"]


async def test_subscribe_live_unknown_entry(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Subscribing to a missing entry returns not found."""
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 10, "type": "pitboss/subscribe_live", "config_entry_id": "missing"}
    )
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == websocket_api_const.ERR_NOT_FOUND


async def test_subscribe_live_ends_when_the_entry_unloads(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """A reload must tell the panel to resubscribe to the new coordinator."""
    config_entry, coordinator = _create_coordinator(hass)
    async_setup_websocket_api(hass)

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 11,
            "type": "pitboss/subscribe_live",
            "config_entry_id": config_entry.entry_id,
        }
    )
    assert (await client.receive_json())["success"]
    await client.receive_json()  # initial snapshot

    for unload_callback in list(config_entry._on_unload or []):
        if (result := unload_callback()) is not None:
            await result

    msg = await client.receive_json()
    assert msg["event"] == {
        "config_entry_id": config_entry.entry_id,
        "unloaded": True,
    }
    assert coordinator._listeners == {}
