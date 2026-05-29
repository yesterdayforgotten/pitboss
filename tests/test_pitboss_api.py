"""Tests for the Pit Boss API client."""

from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession

from custom_components.pitboss.const import (
    INFO_APP,
    INFO_FS_FREE,
    INFO_FS_SIZE,
    INFO_MAC,
    INFO_MODEL_ID,
)
from custom_components.pitboss.pitboss_api import PitbossApi


async def test_update_unique_id_uses_mac_address() -> None:
    """The API should use the device MAC as the stable unique id."""

    api = PitbossApi("192.0.2.10", AsyncMock(spec=ClientSession))

    with patch.object(
        api,
        "_request_json",
        AsyncMock(return_value={"id": "PBL-0F78550", "mac": "AA:BB:CC:DD:EE:FF"}),
    ):
        await api.update_unique_id()

    assert api.get_unique_id() == "aa:bb:cc:dd:ee:ff"
    assert api.get_model() == "PBL-0F78550"
    assert api.get_device_info() == {
        INFO_MODEL_ID: "PBL-0F78550",
        INFO_MAC: "aa:bb:cc:dd:ee:ff",
        INFO_APP: None,
        INFO_FS_SIZE: None,
        INFO_FS_FREE: None,
        "fw_version": None,
        "fw_id": None,
        "mg_version": None,
        "mg_id": None,
        "uptime": None,
        "ram_size": None,
        "ram_free": None,
        "ram_min_free": None,
        "wifi_sta_ip": None,
        "wifi_ap_ip": None,
        "wifi_status": None,
        "wifi_ssid": None,
    }
