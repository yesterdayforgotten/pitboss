"""Support for monitoring Pitboss binary sensors."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import PitbossConfigEntry
from .entity import PitbossEntity
from .pitboss_api import PitbossApi


@dataclass(frozen=True, kw_only=True)
class PitbossBinarySensorEntityMixin:
    """Mixin for Pitboss sensor."""

    value_fn: Callable[[PitbossApi, str], StateType]


@dataclass(frozen=True, kw_only=True)
class PitbossBinarySensorEntityDescription(
    BinarySensorEntityDescription, PitbossBinarySensorEntityMixin
):
    """Describes a Pitboss sensor."""

    available_fn: Callable[[PitbossApi, str], bool] = lambda api, _: True


SENSOR_TYPES: tuple[PitbossBinarySensorEntityDescription, ...] = (
    PitbossBinarySensorEntityDescription(
        key="primer_state",
        translation_key="primer_state",
        icon="mdi:motion",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda api, _: api.get_state_value("Priming"),
    ),
    PitbossBinarySensorEntityDescription(
        key="fan_state",
        translation_key="fan_state",
        icon="mdi:fan",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda api, _: api.get_state_value("FanOn"),
    ),
    PitbossBinarySensorEntityDescription(
        key="igniter_state",
        translation_key="igniter_state",
        icon="mdi:gas-burner",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda api, _: api.get_state_value("IgniterOn"),
    ),
    PitbossBinarySensorEntityDescription(
        key="error_state",
        translation_key="error_state",
        icon="mdi:alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda api, _: api.get_state_value("Error"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PitbossConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Pitboss binary sensors."""
    coordinator = config_entry.runtime_data
    device_id = config_entry.unique_id or config_entry.entry_id

    async_add_entities(
        [
            *(
                PitbossBinarySensor(coordinator, device_id, description)
                for description in SENSOR_TYPES
            ),
            PitbossCookActiveBinarySensor(coordinator, device_id),
            PitbossProbeStallBinarySensor(coordinator, device_id, "P1ActTemp"),
            PitbossProbeStallBinarySensor(coordinator, device_id, "P2ActTemp"),
            PitbossProbeDoneBinarySensor(
                coordinator, device_id, "P1ActTemp", "P1SetTemp"
            ),
            PitbossProbeDoneBinarySensor(
                coordinator, device_id, "P2ActTemp", "P2SetTemp"
            ),
        ]
    )


class PitbossBinarySensor(PitbossEntity, BinarySensorEntity):
    """Representation of a Pitboss binary sensor."""

    entity_description: PitbossBinarySensorEntityDescription

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return super().available and self.entity_description.available_fn(
            self._api, self.entity_description.key
        )

    @property
    def is_on(self) -> bool:
        """Return the sensor state."""
        return bool(
            self.entity_description.value_fn(self._api, self.entity_description.key)
        )


class PitbossProbeStallBinarySensor(PitbossEntity, BinarySensorEntity):
    """Indicate when a probe appears to have plateaued during a cook."""

    _attr_icon = "mdi:thermometer-alert"
    _translation_keys = {
        "P1ActTemp": "p1_stall",
        "P2ActTemp": "p2_stall",
    }

    def __init__(
        self,
        coordinator,
        device_id: str,
        actual_key: str,
    ) -> None:
        """Initialize the probe stall sensor."""
        self._actual_key = actual_key
        super().__init__(
            coordinator,
            device_id,
            BinarySensorEntityDescription(
                key=self._translation_keys[actual_key],
                translation_key=self._translation_keys[actual_key],
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if the probe itself is available."""
        return super().available

    @property
    def is_on(self) -> bool:
        """Return if the probe appears to be stalled."""
        return self.coordinator.is_probe_stalled(self._actual_key)


class PitbossCookActiveBinarySensor(PitbossEntity, BinarySensorEntity):
    """Indicate when a cook session is currently active."""

    _attr_icon = "mdi:grill-outline"

    def __init__(self, coordinator, device_id: str) -> None:
        """Initialize the cook active sensor."""
        super().__init__(
            coordinator,
            device_id,
            BinarySensorEntityDescription(
                key="cook_active",
                translation_key="cook_active",
            ),
        )

    @property
    def is_on(self) -> bool:
        """Return True if a cook session is currently active."""
        return self.coordinator.is_cook_active()


class PitbossProbeDoneBinarySensor(PitbossEntity, BinarySensorEntity):
    """Indicate when a probe has reached its target temperature."""

    _attr_icon = "mdi:thermometer-check"
    _translation_keys = {
        "P1ActTemp": "p1_done",
        "P2ActTemp": "p2_done",
    }

    def __init__(
        self,
        coordinator,
        device_id: str,
        actual_key: str,
        target_key: str,
    ) -> None:
        """Initialize the probe done sensor."""
        self._actual_key = actual_key
        self._target_key = target_key
        super().__init__(
            coordinator,
            device_id,
            BinarySensorEntityDescription(
                key=self._translation_keys[actual_key],
                translation_key=self._translation_keys[actual_key],
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if a target exists for this probe."""
        return super().available and (
            self.coordinator.get_probe_target_temperature(self._target_key) is not None
        )

    @property
    def is_on(self) -> bool:
        """Return if the probe has met or exceeded its target."""
        return self.coordinator.is_probe_done(self._actual_key, self._target_key)
