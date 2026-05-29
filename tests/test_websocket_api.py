"""Tests for the Pitboss websocket cook archive API."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from homeassistant.components.websocket_api import const as websocket_api_const
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
            "message": "NoPellets",
            "end_timestamp": probe_removed_at.isoformat(),
        },
        {
            "timestamp": msg["result"]["cook"]["errors"][1]["timestamp"],
            "source": "update",
            "message": "Communication error while updating Pit Boss state: boom",
        },
    ]
