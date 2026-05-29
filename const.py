"""Constants for the Pitboss integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "pitboss"

DATA_DEVICE_INFO = "device_info"

INFO_APP = "app"
INFO_FS_FREE = "fs_free"
INFO_FS_SIZE = "fs_size"
INFO_FW_ID = "fw_id"
INFO_FW_VERSION = "fw_version"
INFO_MAC = "mac"
INFO_MG_ID = "mg_id"
INFO_MG_VERSION = "mg_version"
INFO_MODEL_ID = "model_id"
INFO_RAM_FREE = "ram_free"
INFO_RAM_MIN_FREE = "ram_min_free"
INFO_RAM_SIZE = "ram_size"
INFO_UPTIME = "uptime"
INFO_WIFI_AP_IP = "wifi_ap_ip"
INFO_WIFI_SSID = "wifi_ssid"
INFO_WIFI_STA_IP = "wifi_sta_ip"
INFO_WIFI_STATUS = "wifi_status"

DEFAULT_NAME = "Pit Boss"
DEFAULT_SCAN_INTERVAL = 15  # seconds
DISCOVERY_PARALLELISM = 32
DISCOVERY_TIMEOUT_SECONDS = 1
SUPPORTED_MODEL_IDS = {"PBL-0F78550"}
SUPPORTED_MODELS = SUPPORTED_MODEL_IDS
COOK_CONFIRMATION_WINDOW = timedelta(hours=1)
COOK_END_GRACE_PERIOD = timedelta(minutes=30)
COOK_SAMPLE_INTERVAL = timedelta(minutes=5)
COOK_STORAGE_SAVE_DELAY = 30
COOK_STORAGE_VERSION = 2
COOK_DETAIL_STORAGE_VERSION = 1
DONE_CONFIRMATION_WINDOW = timedelta(minutes=5)
STALL_CONFIRMATION_WINDOW = timedelta(minutes=20)
STALL_MINIMUM_TEMPERATURE_C = 60
STALL_MINIMUM_TEMPERATURE_F = 140
STALL_TREND_THRESHOLD = 2.0
TEMPERATURE_TREND_INTERVAL = timedelta(hours=1)
TEMPERATURE_TREND_WINDOW = timedelta(minutes=30)
TEMPERATURE_COMMAND_DEBOUNCE = 0.75
UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]
