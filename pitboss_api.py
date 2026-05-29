"""Pit Boss local HTTP API client used by the custom integration."""

from enum import Enum
import logging
import re
from struct import error as StructError, unpack
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from homeassistant.helpers.device_registry import format_mac

from .const import (
    INFO_APP,
    INFO_FS_FREE,
    INFO_FS_SIZE,
    INFO_FW_ID,
    INFO_FW_VERSION,
    INFO_MAC,
    INFO_MG_ID,
    INFO_MG_VERSION,
    INFO_MODEL_ID,
    INFO_RAM_FREE,
    INFO_RAM_MIN_FREE,
    INFO_RAM_SIZE,
    INFO_UPTIME,
    INFO_WIFI_AP_IP,
    INFO_WIFI_SSID,
    INFO_WIFI_STA_IP,
    INFO_WIFI_STATUS,
)

TEMP_NA = 960
REQUEST_TIMEOUT = ClientTimeout(total=10)

_LOGGER = logging.getLogger(__name__)


class PitbossApi:
    """Small client for interacting with Pit Boss local RPC endpoints."""

    _debug = False

    class Command(Enum):
        """Supported Pit Boss command opcodes."""

        SetPowerState = "01"
        SetTemperature = "05"
        SetConnectedStatus = "24"
        GetStatus11 = "0B"
        GetStatus12 = "0C"
        ControlPrimeMotor = "08"
        ControlLight = "02"
        SetTempFC = "09"

    class Temp(Enum):
        """Temperature control target selectors."""

        Grill = "01"
        Probe1 = "02"

    @staticmethod
    def _initial_state() -> dict:
        """Return an empty state payload for this device instance."""

        return {
            "PowerOn": False,
            "FanOn": False,
            "IgniterOn": False,
            "MotorOn": False,
            "LightOn": False,
            "Priming": False,
            "P1SetTemp": 0,
            "P1ActTemp": 0,
            "P2ActTemp": 0,
            "P3ActTemp": 0,
            "P4ActTemp": 0,
            "GrillSetTemp": 0,
            "GrillActTemp": 0,
            "IsFarenheit": False,
            "Errors": {
                "Err1": False,
                "Err2": False,
                "Err3": False,
                "HighTempErr": False,
                "FanErr": False,
                "HotErr": False,
                "MotorErr": False,
                "NoPellets": False,
                "ErL": False,
            },
            "Error": False,
            "ErrorStr": "",
            "Recipe": {
                "RecipeStep": 0,
                "TimeH": 0,
                "TimeM": 0,
                "TimeS": 0,
            },
        }

    @staticmethod
    def _initial_device_info() -> dict[str, Any]:
        """Return an empty normalized device-info payload."""

        return {
            INFO_MODEL_ID: "",
            INFO_MAC: "",
            INFO_APP: None,
            INFO_FS_SIZE: None,
            INFO_FS_FREE: None,
            INFO_FW_VERSION: None,
            INFO_FW_ID: None,
            INFO_MG_VERSION: None,
            INFO_MG_ID: None,
            INFO_UPTIME: None,
            INFO_RAM_SIZE: None,
            INFO_RAM_FREE: None,
            INFO_RAM_MIN_FREE: None,
            INFO_WIFI_STA_IP: None,
            INFO_WIFI_AP_IP: None,
            INFO_WIFI_STATUS: None,
            INFO_WIFI_SSID: None,
        }

    @staticmethod
    def normalize_device_info(info: dict[str, Any]) -> dict[str, Any]:
        """Normalize the Pit Boss Sys.GetInfo payload."""

        wifi = info.get("wifi") or {}
        return {
            INFO_MODEL_ID: info.get("id", ""),
            INFO_MAC: format_mac(info.get("mac", "")),
            INFO_APP: info.get("app"),
            INFO_FS_SIZE: info.get("fs_size"),
            INFO_FS_FREE: info.get("fs_free"),
            INFO_FW_VERSION: info.get("fw_version"),
            INFO_FW_ID: info.get("fw_id"),
            INFO_MG_VERSION: info.get("mg_version"),
            INFO_MG_ID: info.get("mg_id"),
            INFO_UPTIME: info.get("uptime"),
            INFO_RAM_SIZE: info.get("ram_size"),
            INFO_RAM_FREE: info.get("ram_free"),
            INFO_RAM_MIN_FREE: info.get("ram_min_free"),
            INFO_WIFI_STA_IP: wifi.get("sta_ip"),
            INFO_WIFI_AP_IP: wifi.get("ap_ip"),
            INFO_WIFI_STATUS: wifi.get("status"),
            INFO_WIFI_SSID: wifi.get("ssid"),
        }

    @staticmethod
    def temp2hex(val: int) -> str:
        """Encode a temperature integer to the protocol hex payload format."""

        temp = f"{val:3d}"
        return re.sub(r"(\d)(\d)(\d)", r"0\g<1>0\g<2>0\g<3>", temp)

    def __init__(self, host: str, session: ClientSession) -> None:
        """Initialize the API client for a smoker host."""

        self._host = host
        self._url = f"http://{self._host}/rpc"
        self._session = session
        self._state = self._initial_state()
        self._device_info = self._initial_device_info()

    @staticmethod
    def hex2temp(val: bytes) -> int:
        """Decode a protocol temperature field into an integer value."""

        decoded = val[0] * 100 + val[1] * 10 + val[2]
        return 0 if decoded == TEMP_NA else decoded

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an HTTP request against the device RPC endpoint and decode JSON."""

        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        async with self._session.request(
            method, f"{self._url}/{path}", **kwargs
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def _request_text(self, method: str, path: str, **kwargs: Any) -> str:
        """Perform an HTTP request against the device RPC endpoint and decode text."""

        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        async with self._session.request(
            method, f"{self._url}/{path}", **kwargs
        ) as response:
            response.raise_for_status()
            return await response.text()

    async def send_command(self, cmd: Command, val: str) -> None:
        """Send a raw MCU command to the smoker."""

        Header = "FE"
        Postamble = "FF"
        packet = Header + cmd.value + val + Postamble

        resp = await self._request_text(
            "post", "PB.SendMCUCommand", json={"command": packet}
        )
        if self._debug:
            _LOGGER.debug("PB.SendMCUCommand response: %s", resp)

    async def set_grill_temp(self, temp: float) -> None:
        """Set the grill target temperature."""

        await self.send_command(
            PitbossApi.Command.SetTemperature,
            PitbossApi.Temp.Grill.value + PitbossApi.temp2hex(int(temp)),
        )

    async def set_probe1_temp(self, temp: float) -> None:
        """Set the probe 1 target temperature."""

        await self.send_command(
            PitbossApi.Command.SetTemperature,
            PitbossApi.Temp.Probe1.value + PitbossApi.temp2hex(int(temp)),
        )

    async def set_prime_state(self, state: bool) -> None:
        """Enable or disable priming mode."""

        await self.send_command(
            PitbossApi.Command.ControlPrimeMotor,
            "01" if state else "00",
        )

    async def set_mcu_update_frequency(self, freq: int) -> None:
        """Set the smoker MCU reporting frequency."""

        resp = await self._request_text(
            "post",
            "PB.SetMCU_UpdateFrequency",
            json={"frequency": freq},
        )
        if self._debug:
            _LOGGER.debug("PB.SetMCU_UpdateFrequency response: %s", resp)

    async def set_power_state(self, val: bool) -> None:
        """Turn the smoker on or off."""

        await self.send_command(
            PitbossApi.Command.SetPowerState,
            "01" if val else "02",
        )

    async def update_unique_id(self) -> None:
        """Fetch and cache the smoker unique id."""

        await self.update_device_info()

    async def update_device_info(
        self, *, timeout: ClientTimeout | None = None
    ) -> dict[str, Any]:
        """Fetch and cache the smoker identity and model information."""

        info = await self._request_json(
            "get",
            "Sys.GetInfo",
            timeout=timeout or REQUEST_TIMEOUT,
        )
        device_info = self.normalize_device_info(info)
        unique_id = device_info[INFO_MAC]
        if not unique_id:
            raise ValueError("Pit Boss info response did not include a device mac")
        model = device_info[INFO_MODEL_ID]
        if not model:
            raise ValueError("Pit Boss info response did not include a device model")
        self._device_info = device_info
        return dict(self._device_info)

    def set_device_info(self, device_info: dict[str, Any]) -> None:
        """Seed the cached normalized device info."""

        self._device_info = {
            **self._initial_device_info(),
            **device_info,
        }

    def get_unique_id(self) -> str:
        """Return the cached smoker unique id."""

        return self._device_info[INFO_MAC]

    def get_model(self) -> str:
        """Return the cached smoker model id."""

        return self._device_info[INFO_MODEL_ID]

    def get_device_info(self) -> dict[str, Any]:
        """Return the cached normalized device info."""

        return dict(self._device_info)

    def get_device_info_value(self, key: str) -> Any:
        """Return one cached device-info value."""

        return self._device_info.get(key)

    async def update_state(self) -> None:
        """Fetch and decode the current smoker state payload."""

        payload = await self._request_json("get", "PB.GetState")
        if self._debug:
            _LOGGER.debug("PB.GetState payload: %s", payload)

        try:
            sc12 = bytes.fromhex(payload["sc_12"])
            sc11 = bytes.fromhex(payload["sc_11"])
        except (KeyError, ValueError) as err:
            raise ValueError("Pit Boss state payload is malformed") from err

        if sc12 == b"" or sc11 == b"":
            raise ValueError("Pit Boss state payload was empty")

        try:
            (
                P1SetTemp,
                P1ActTemp,
                P2ActTemp,
                P3ActTemp,
                P4ActTemp,
                SmokerActTemp,
                GrillSetTemp,
                GrillActTemp,
                self._state["IsFarenheit"],
            ) = unpack("xx3s3s3s3s3s3s3s3s?x", sc12)

            (
                P1SetTemp,
                P1ActTemp,
                P2ActTemp,
                P3ActTemp,
                P4ActTemp,
                SmokerActTemp,
                _misc_temp,
                _misc_temp_sel,
                ModuleIsOn,
                self._state["Errors"]["Err1"],
                self._state["Errors"]["Err2"],
                self._state["Errors"]["Err3"],
                self._state["Errors"]["HighTempErr"],
                self._state["Errors"]["FanErr"],
                self._state["Errors"]["HotErr"],
                self._state["Errors"]["MotorErr"],
                self._state["Errors"]["NoPellets"],
                self._state["Errors"]["ErL"],
                self._state["FanOn"],
                self._state["IgniterOn"],
                self._state["MotorOn"],
                self._state["LightOn"],
                self._state["Priming"],
                self._state["IsFarenheit"],
                self._state["Recipe"]["RecipeStep"],
                self._state["Recipe"]["TimeH"],
                self._state["Recipe"]["TimeM"],
                self._state["Recipe"]["TimeS"],
            ) = unpack("xx3s3s3s3s3s3s3sBB???????????????BBBBx", sc11)
        except StructError as err:
            raise ValueError("Pit Boss state payload had an invalid format") from err

        self._state["P1SetTemp"] = PitbossApi.hex2temp(P1SetTemp)
        self._state["P1ActTemp"] = PitbossApi.hex2temp(P1ActTemp)
        self._state["P2ActTemp"] = PitbossApi.hex2temp(P2ActTemp)
        self._state["P3ActTemp"] = PitbossApi.hex2temp(P3ActTemp)
        self._state["P4ActTemp"] = PitbossApi.hex2temp(P4ActTemp)
        self._state["SmokerActTemp"] = PitbossApi.hex2temp(SmokerActTemp)
        self._state["GrillSetTemp"] = PitbossApi.hex2temp(GrillSetTemp)
        self._state["GrillActTemp"] = PitbossApi.hex2temp(GrillActTemp)

        self._state["PowerOn"] = ModuleIsOn == 1

        active_errors = [
            name for name, active in self._state["Errors"].items() if active
        ]
        self._state["Error"] = bool(active_errors)
        self._state["ErrorStr"] = " ".join(active_errors)

    def get_state_value(self, key: str):
        """Return a cached state value by key."""

        return self._state[key]

    def apply_optimistic_state(self, state: dict) -> None:
        """Write expected state values immediately after a command.

        Allows the UI to reflect the commanded state before the next poll
        confirms it. Only keys that already exist in the state are updated.
        """
        for key, value in state.items():
            if key in self._state:
                self._state[key] = value
