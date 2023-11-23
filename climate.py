from __future__ import annotations

import logging
from typing import Any

from .pitboss_api import PitbossApi
from .entity import PitbossEntity
from .coordinator import PitbossDataUpdateCoordinator

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    ATTR_TEMPERATURE, UnitOfTemperature
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityDescription

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Pitboss climate platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            PitbossClimate(coordinator, config_entry.unique_id,
                           EntityDescription(
                               key="grill_control",
                               translation_key="grill_control",
                           )),
            PitbossP1Climate(coordinator, config_entry.unique_id,
                             EntityDescription(
                                 key="probe1_control",
                                 translation_key="probe1_control",
                             )),
        ]
    )


class PitbossClimate(PitbossEntity, ClimateEntity):
    """Representation of a Pitboss climate device."""

    entity_description: EntityDescription

    _attr_max_temp = 400
    _attr_min_temp = 130
    _attr_target_temperature_step = 10
    _attr_precision = 1
    _attr_icon = "mdi:grill"
    _attr_hvac_modes = [
        HVACMode.OFF.value,
        HVACMode.HEAT.value,
    ]

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
        )
        return supported_features

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        if self._api.GetStateValue('IsFarenheit') == False:
            return UnitOfTemperature.CELSIUS

        return UnitOfTemperature.FAHRENHEIT

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._api.GetStateValue('GrillActTemp')

    @property
    def target_temperature(self):
        """Return the temperature we are trying to reach."""
        return self._api.GetStateValue('GrillSetTemp')

    @property
    def hvac_mode(self):
        """Return hvac target hvac state."""
        if not self._api.GetStateValue('PowerOn'):
            return HVACMode.OFF

        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        if not self._api.GetStateValue('PowerOn'):
            return HVACAction.OFF
        elif self._api.GetStateValue('IgniterOn'):
            return HVACAction.PREHEATING
        elif self._api.GetStateValue('Priming'):
            return HVACAction.HEATING
        elif self._api.GetStateValue('FanOn'):
            return HVACAction.FAN

        return HVACAction.IDLE

    @property
    def fan(self):
        """Return the current fan status."""
        if self._api.GetStateValue('FanOn'):
            return STATE_ON
        return STATE_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperatures."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            _LOGGER.debug("Setting temp of %s to %s",
                          self.unique_id, str(temp))
            await self.hass.async_add_executor_job(self._api.SetGrillTemp, temp)
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new operation mode."""
        _LOGGER.debug("Setting operation mode of %s to %s",
                      self.unique_id, hvac_mode)

        if hvac_mode == HVACMode.HEAT:
            await self.async_turn_on()
        else:
            await self.async_turn_off()

    async def async_turn_on(self) -> None:
        """Turn on."""
        _LOGGER.debug("Turning %s on", self.unique_id)
        await self.hass.async_add_executor_job(self._api.SetPowerState, True)
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off."""
        _LOGGER.debug("Turning %s off", self.unique_id)
        await self.hass.async_add_executor_job(self._api.SetPowerState, False)
        self.async_write_ha_state()

    @property
    def _api(self) -> PitbossApi:
        """Return to api from coordinator."""
        return self.coordinator.api


class PitbossP1Climate(PitbossEntity, ClimateEntity):
    """Representation of a Pitboss climate device."""

    _attr_max_temp = 400
    _attr_min_temp = 0
    _attr_target_temperature_step = 1
    _attr_precision = 1
    _attr_icon = "mdi:thermometer-lines"
    _attr_hvac_modes = None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
        )
        return supported_features

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        if self._api.GetStateValue('IsFarenheit') == False:
            return UnitOfTemperature.CELSIUS

        return UnitOfTemperature.FAHRENHEIT

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._api.GetStateValue('P1ActTemp')

    @property
    def target_temperature(self):
        """Return the temperature we are trying to reach."""
        return self._api.GetStateValue('P1SetTemp')

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperatures."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            _LOGGER.debug("Setting temp of %s to %s",
                          self.unique_id, str(temp))
            await self.hass.async_add_executor_job(self._api.SetProbe1Temp, temp)
            self.async_write_ha_state()

    @property
    def hvac_mode(self):
        """Return hvac target hvac state."""
        return None
#
#    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
#        """Set new operation mode."""
#        _LOGGER.debug("Setting operation mode of %s to %s",
#                      self.unique_id, hvac_mode)

    @property
    def _api(self) -> PitbossApi:
        """Return to api from coordinator."""
        return self.coordinator.api

#    @property
#    def hvac_action(self) -> HVACAction:
#        return HVACAction.IDLE

    @property
    def state(self) -> str | None:
        if self.current_temperature >= self.target_temperature:
            return "Done"
        else:
            return "Waiting"
