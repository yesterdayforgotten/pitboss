"""Support for monitoring Pitboss sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .pitboss_api import PitbossApi
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .entity import PitbossEntity


@dataclass
class PitbossBinarySensorEntityMixin:
    """Mixin for Pitboss sensor."""

    value_fn: Callable[[PitbossApi, str], StateType | datetime]


@dataclass
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
        value_fn=lambda api, _: api.GetStateValue('Priming'),
    ),
    PitbossBinarySensorEntityDescription(
        key="fan_state",
        translation_key="fan_state",
        icon="mdi:fan",
        value_fn=lambda api, _: api.GetStateValue('FanOn'),
    ),
    PitbossBinarySensorEntityDescription(
        key="igniter_state",
        translation_key="igniter_state",
        icon="mdi:gas-burner",
        value_fn=lambda api, _: api.GetStateValue('IgniterOn'),
    ),
    PitbossBinarySensorEntityDescription(
        key="error_state",
        translation_key="error_state",
        icon="mdi:alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda api, _: api.GetStateValue('Error'),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Pitboss binary sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        PitbossBinarySensor(coordinator, config_entry.unique_id, description) for description in SENSOR_TYPES
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
        return self.entity_description.value_fn(self._api, self.entity_description.key)
