"""Support for monitoring Pitboss sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import PitbossConfigEntry
from .const import (
    INFO_FS_FREE,
    INFO_FS_SIZE,
    INFO_FW_ID,
    INFO_FW_VERSION,
    INFO_MG_ID,
    INFO_MG_VERSION,
    INFO_RAM_FREE,
    INFO_RAM_MIN_FREE,
    INFO_RAM_SIZE,
    INFO_UPTIME,
    INFO_WIFI_AP_IP,
    INFO_WIFI_SSID,
    INFO_WIFI_STA_IP,
    INFO_WIFI_STATUS,
    TEMPERATURE_TREND_INTERVAL,
)
from .coordinator import PitbossDataUpdateCoordinator
from .entity import PitbossEntity
from .pitboss_api import PitbossApi


@dataclass(frozen=True, kw_only=True)
class PitbossSensorEntityMixin:
    """Mixin for Pitboss sensor."""

    value_fn: Callable[[PitbossApi, str], StateType]


@dataclass(frozen=True, kw_only=True)
class PitbossSensorEntityDescription(SensorEntityDescription, PitbossSensorEntityMixin):
    """Describes a Pitboss sensor."""

    available_fn: Callable[[PitbossApi, str], bool] = lambda api, _: True


SENSOR_TYPES: tuple[PitbossSensorEntityDescription, ...] = (
    PitbossSensorEntityDescription(
        key="p1_act_temp",
        translation_key="p1_act_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer",
        value_fn=lambda api, _: api.get_state_value("P1ActTemp"),
    ),
    PitbossSensorEntityDescription(
        key="p2_act_temp",
        translation_key="p2_act_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer",
        value_fn=lambda api, _: api.get_state_value("P2ActTemp"),
    ),
    PitbossSensorEntityDescription(
        key="error_details",
        translation_key="error_details",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert",
        value_fn=lambda api, _: api.get_state_value("ErrorStr"),
    ),
    PitbossSensorEntityDescription(
        key=INFO_UPTIME,
        translation_key="uptime",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_RAM_SIZE,
        translation_key="ram_size",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_RAM_FREE,
        translation_key="ram_free",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:memory-arrow-down",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_RAM_MIN_FREE,
        translation_key="ram_min_free",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:memory-arrow-down",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_FW_VERSION,
        translation_key="fw_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:chip",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_FW_ID,
        translation_key="fw_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:identifier",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_MG_VERSION,
        translation_key="mg_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:chip",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_MG_ID,
        translation_key="mg_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:identifier",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_FS_SIZE,
        translation_key="fs_size",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:harddisk",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_FS_FREE,
        translation_key="fs_free",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:harddisk-plus",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_WIFI_STA_IP,
        translation_key="wifi_sta_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:wifi-marker",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_WIFI_AP_IP,
        translation_key="wifi_ap_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:wifi-marker",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_WIFI_STATUS,
        translation_key="wifi_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:wifi-cog",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
    PitbossSensorEntityDescription(
        key=INFO_WIFI_SSID,
        translation_key="wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:wifi-star",
        value_fn=lambda api, key: api.get_device_info_value(key),
        available_fn=lambda api, key: api.get_device_info_value(key) is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PitbossConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Pitboss sensors."""
    coordinator = config_entry.runtime_data
    device_id = config_entry.unique_id or config_entry.entry_id

    async_add_entities(
        [
            *(
                PitbossSensor(coordinator, device_id, description)
                for description in SENSOR_TYPES
            ),
            PitbossCurrentCookDurationSensor(coordinator, device_id),
            PitbossLastCookDurationSensor(coordinator, device_id),
            PitbossLastCookStartSensor(coordinator, device_id),
            PitbossLastCookEndSensor(coordinator, device_id),
            PitbossProbeTemperatureDeltaSensor(
                coordinator, device_id, "P1ActTemp", "P1SetTemp"
            ),
            PitbossProbeTemperatureDeltaSensor(
                coordinator, device_id, "P2ActTemp", "P2SetTemp"
            ),
            PitbossTemperatureRateSensor(coordinator, device_id, "GrillActTemp"),
            PitbossTemperatureRateSensor(coordinator, device_id, "P1ActTemp"),
            PitbossTemperatureRateSensor(coordinator, device_id, "P2ActTemp"),
            PitbossTimeSinceTargetReachedSensor(
                coordinator, device_id, "P1ActTemp", "P1SetTemp"
            ),
            PitbossTimeSinceTargetReachedSensor(
                coordinator, device_id, "P2ActTemp", "P2SetTemp"
            ),
            PitbossLastSuccessfulUpdateSensor(coordinator, device_id),
        ]
    )


class PitbossSensor(PitbossEntity, SensorEntity):
    """Representation of a Pitboss sensor."""

    entity_description: PitbossSensorEntityDescription

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement for temperature sensors."""
        if self.entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            if not self._api.get_state_value("IsFarenheit"):
                return UnitOfTemperature.CELSIUS
            return UnitOfTemperature.FAHRENHEIT
        return self.entity_description.native_unit_of_measurement

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return super().available and self.entity_description.available_fn(
            self._api, self.entity_description.key
        )

    @property
    def native_value(self) -> StateType:
        """Return the sensor state."""
        return self.entity_description.value_fn(self._api, self.entity_description.key)


class PitbossLastSuccessfulUpdateSensor(PitbossEntity, SensorEntity):
    """Timestamp of the last successful device update."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the last successful update sensor."""
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key="last_successful_update",
                translation_key="last_successful_update",
            ),
        )

    @property
    def available(self) -> bool:
        """Keep the timestamp visible even when the smoker is offline."""
        return True

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last successful poll."""
        return self.coordinator.last_update_success_time


class PitbossCurrentCookDurationSensor(PitbossEntity, SensorEntity):
    """Duration of the currently active cook."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:timer-play-outline"

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the current cook duration sensor."""
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key="current_cook_duration",
                translation_key="current_cook_duration",
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if a confirmed cook is active."""
        return self.coordinator.get_current_cook_duration() is not None

    @property
    def native_value(self) -> float | None:
        """Return minutes since the confirmed cook started."""
        if (elapsed := self.coordinator.get_current_cook_duration()) is None:
            return None
        return round(elapsed.total_seconds() / 60, 1)


class PitbossLastCookDurationSensor(PitbossEntity, SensorEntity):
    """Duration of the most recently completed cook."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:timer-stop-outline"

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the last cook duration sensor."""
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key="last_cook_duration",
                translation_key="last_cook_duration",
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if a completed cook is available."""
        return self.coordinator.get_last_cook_duration() is not None

    @property
    def native_value(self) -> float | None:
        """Return minutes for the most recently completed cook."""
        if (elapsed := self.coordinator.get_last_cook_duration()) is None:
            return None
        return round(elapsed.total_seconds() / 60, 1)


class PitbossLastCookStartSensor(PitbossEntity, SensorEntity):
    """Start time of the most recently completed cook."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-start"

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the last cook start sensor."""
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key="last_cook_start",
                translation_key="last_cook_start",
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if a completed cook is available."""
        return self.coordinator.get_last_cook_start() is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the start time of the most recently completed cook."""
        return self.coordinator.get_last_cook_start()


class PitbossLastCookEndSensor(PitbossEntity, SensorEntity):
    """End time of the most recently completed cook."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-end"

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the last cook end sensor."""
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key="last_cook_end",
                translation_key="last_cook_end",
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if a completed cook is available."""
        return self.coordinator.get_last_cook_end() is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the end time of the most recently completed cook."""
        return self.coordinator.get_last_cook_end()


class PitbossTemperatureRateSensor(PitbossEntity, SensorEntity):
    """Derived temperature rate-of-change sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:thermometer-chevron-up"
    _rate_translation_keys = {
        "GrillActTemp": "smoker_temp_rate",
        "P1ActTemp": "p1_temp_rate",
        "P2ActTemp": "p2_temp_rate",
    }

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
        state_key: str,
    ) -> None:
        """Initialize the temperature rate sensor."""
        self._state_key = state_key
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key=self._rate_translation_keys[state_key],
                translation_key=self._rate_translation_keys[state_key],
            ),
        )

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the rate unit using the current temperature mode."""
        base_unit = (
            UnitOfTemperature.CELSIUS
            if not self._api.get_state_value("IsFarenheit")
            else UnitOfTemperature.FAHRENHEIT
        )
        return (
            f"{base_unit}/{int(TEMPERATURE_TREND_INTERVAL.total_seconds() // 3600)} hr"
        )

    @property
    def native_value(self) -> float | None:
        """Return the derived temperature change rate."""
        return self.coordinator.get_temperature_change_rate(self._state_key)


class PitbossProbeTemperatureDeltaSensor(PitbossEntity, SensorEntity):
    """Difference between probe target and actual temperature."""

    _attr_icon = "mdi:thermometer-minus"
    _delta_translation_keys = {
        "P1ActTemp": "p1_temp_delta",
        "P2ActTemp": "p2_temp_delta",
    }
    _target_keys = {
        "P1ActTemp": "P1SetTemp",
        "P2ActTemp": "P2SetTemp",
    }

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
        actual_key: str,
        target_key: str,
    ) -> None:
        """Initialize the probe delta sensor."""
        self._actual_key = actual_key
        self._target_key = target_key
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key=self._delta_translation_keys[actual_key],
                translation_key=self._delta_translation_keys[actual_key],
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if a target is available for the probe."""
        return super().available and (
            self.coordinator.get_probe_target_temperature(self._target_key) is not None
        )

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement using the current temperature mode."""
        if not self._api.get_state_value("IsFarenheit"):
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def native_value(self) -> float | None:
        """Return target minus actual temperature."""
        return self.coordinator.get_probe_temperature_delta(
            self._actual_key, self._target_key
        )


class PitbossTimeSinceTargetReachedSensor(PitbossEntity, SensorEntity):
    """Duration since a probe last reached its target temperature."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:timer-check-outline"
    _translation_keys = {
        "P1ActTemp": "p1_time_since_target_reached",
        "P2ActTemp": "p2_time_since_target_reached",
    }

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
        actual_key: str,
        target_key: str,
    ) -> None:
        """Initialize the time-since-target-reached sensor."""
        self._target_key = target_key
        super().__init__(
            coordinator,
            device_id,
            SensorEntityDescription(
                key=self._translation_keys[actual_key],
                translation_key=self._translation_keys[actual_key],
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if a target is available for the probe."""
        return super().available and (
            self.coordinator.get_probe_target_temperature(self._target_key) is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return minutes since the probe most recently reached target."""
        if (
            elapsed := self.coordinator.get_time_since_target_reached(self._target_key)
        ) is None:
            return None
        return round(elapsed.total_seconds() / 60, 1)
