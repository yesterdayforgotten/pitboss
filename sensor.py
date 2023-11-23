"""Support for monitoring Pitboss sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .pitboss_api import PitbossApi
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util.dt import utcnow
from homeassistant.util.variance import ignore_variance

from .const import DOMAIN
from .entity import PitbossEntity


@dataclass
class PitbossSensorEntityMixin:
    """Mixin for Pitboss sensor."""

    value_fn: Callable[[PitbossApi, str], StateType | datetime]


@dataclass
class PitbossSensorEntityDescription(
    SensorEntityDescription, PitbossSensorEntityMixin
):
    """Describes a Pitboss sensor."""

    available_fn: Callable[[PitbossApi, str], bool] = lambda api, _: True


SENSOR_TYPES: tuple[PitbossSensorEntityDescription, ...] = (
    # PitbossSensorEntityDescription(
    #    key="grill_act_temp",
    #    translation_key="grill_act_temp",
    #    device_class=SensorDeviceClass.TEMPERATURE,
    #    native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    #    state_class=SensorStateClass.MEASUREMENT,
    #    value_fn=lambda api, _: api.GetStateValue('GrillActTemp'),
    # ),
    #    PitbossSensorEntityDescription(
    #        key="grill_target_temp",
    #        translation_key="grill_target_temp",
    #        device_class=SensorDeviceClass.TEMPERATURE,
    #        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    #        state_class=SensorStateClass.MEASUREMENT,
    #        entity_category=EntityCategory.DIAGNOSTIC,
    #        icon="mdi:printer-3d",
    #        value_fn=lambda api, _: api.GetStateValue('GrillSetTemp'),
    #    ),
    PitbossSensorEntityDescription(
        key="p1_act_temp",
        translation_key="p1_act_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer",
        value_fn=lambda api, _: api.GetStateValue('P1ActTemp'),
    ),
    PitbossSensorEntityDescription(
        key="p1_target_temp",
        translation_key="p1_target_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer-check",
        value_fn=lambda api, _: api.GetStateValue('P1SetTemp'),
    ),
    PitbossSensorEntityDescription(
        key="p2_act_temp",
        translation_key="p2_act_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer",
        value_fn=lambda api, _: api.GetStateValue('P2ActTemp'),
    ),
    PitbossSensorEntityDescription(
        key="error_details",
        translation_key="error_details",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:alert",
        value_fn=lambda api, _: api.GetStateValue('ErrorStr'),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Pitboss sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        PitbossSensor(coordinator, config_entry.unique_id, description) for description in SENSOR_TYPES
    )


class PitbossSensor(PitbossEntity, SensorEntity):
    """Representation of a Pitboss sensor."""

    entity_description: PitbossSensorEntityDescription

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return super().available and self.entity_description.available_fn(
            self._api, self.entity_description.key
        )

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor state."""
        return self.entity_description.value_fn(self._api, self.entity_description.key)
