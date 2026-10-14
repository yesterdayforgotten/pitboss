"""Tests for the Pit Boss API client."""

from unittest.mock import AsyncMock, patch

from aiohttp import ClientResponseError, ClientSession
import pytest

from custom_components.pitboss.const import (
    INFO_APP,
    INFO_FS_FREE,
    INFO_FS_SIZE,
    INFO_MAC,
    INFO_MODEL_ID,
)
from custom_components.pitboss.pitboss_api import PitbossApi, describe_errors


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


def test_temp2hex_pads_values_below_100() -> None:
    """Every digit is sent as its own byte, including leading zeros."""

    assert PitbossApi.temp2hex(225) == "020205"
    assert PitbossApi.temp2hex(74) == "000704"
    assert PitbossApi.temp2hex(5) == "000005"


async def test_is_pitboss_checks_the_pb_rpc_namespace() -> None:
    """Any controller id is accepted as long as PB.GetState answers."""

    api = PitbossApi("192.0.2.10", AsyncMock(spec=ClientSession))

    with patch.object(
        api, "_request_json", AsyncMock(return_value={"sc_11": "", "sc_12": ""})
    ):
        assert await api.async_is_pitboss()

    not_found = ClientResponseError(request_info=None, history=(), status=404)
    with patch.object(api, "_request_json", AsyncMock(side_effect=not_found)):
        assert not await api.async_is_pitboss()


async def test_update_device_info_rejects_non_object_payload() -> None:
    """A non-dict Sys.GetInfo body must not crash discovery."""

    api = PitbossApi("192.0.2.10", AsyncMock(spec=ClientSession))

    with (
        patch.object(api, "_request_json", AsyncMock(return_value=["nope"])),
        pytest.raises(ValueError),
    ):
        await api.update_device_info()


def test_describe_errors_uses_plain_language() -> None:
    """Controller error flags are shown as readable text; unknown ones pass through."""

    assert describe_errors("") == ""
    assert describe_errors("NoPellets") == "Out of pellets"
    assert describe_errors("NoPellets NewErr") == "Out of pellets; NewErr"
