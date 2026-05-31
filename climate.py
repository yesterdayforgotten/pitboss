"""Climate platform for the Pit Boss integration."""

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter

from . import PitbossConfigEntry
from .const import TEMPERATURE_COMMAND_DEBOUNCE
from .entity import PitbossEntity

_LOGGER = logging.getLogger(__name__)

_GRILL_MIN_TEMP_F = 130
_GRILL_MAX_TEMP_F = 400


def _grill_limit_in_active_unit(is_fahrenheit: bool, value_f: int) -> float:
    """Return a grill temperature limit in the active unit."""
    if is_fahrenheit:
        return float(value_f)

    return TemperatureConverter.convert(
        value_f,
        UnitOfTemperature.FAHRENHEIT,
        UnitOfTemperature.CELSIUS,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PitbossConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Pitboss climate platform."""
    coordinator = config_entry.runtime_data
    device_id = config_entry.unique_id or config_entry.entry_id
    async_add_entities(
        [
            PitbossClimate(
                coordinator,
                device_id,
                EntityDescription(
                    key="grill_control",
                    translation_key="grill_control",
                ),
            ),
        ]
    )


class PitbossClimate(PitbossEntity, ClimateEntity):
    """Representation of a Pitboss climate device."""

    entity_description: EntityDescription

    _attr_target_temperature_step = 10
    _attr_precision = 1
    _attr_icon = "mdi:grill"
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
    ]

    @property
    def _is_fahrenheit(self) -> bool:
        """Return True when the smoker reports Fahrenheit mode."""
        return self._api.is_fahrenheit()

    @property
    def _is_power_on(self) -> bool:
        """Return True when the smoker reports power on."""
        return bool(self._api.get_state_value("PowerOn"))

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        if not self._is_fahrenheit:
            return UnitOfTemperature.CELSIUS

        return UnitOfTemperature.FAHRENHEIT

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return _grill_limit_in_active_unit(self._is_fahrenheit, _GRILL_MAX_TEMP_F)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return _grill_limit_in_active_unit(self._is_fahrenheit, _GRILL_MIN_TEMP_F)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._api.get_state_value("GrillActTemp")

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we are trying to reach."""
        return self._api.get_state_value("GrillSetTemp")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac target hvac state."""
        if not self._is_power_on:
            return HVACMode.OFF

        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac action."""
        if not self._is_power_on:
            if self._api.get_state_value("FanOn"):
                return HVACAction.FAN
            return HVACAction.OFF
        if self._api.get_state_value("IgniterOn"):
            return HVACAction.PREHEATING
        if self._api.get_state_value("Priming"):
            return HVACAction.HEATING
        if self._api.get_state_value("FanOn"):
            return HVACAction.FAN

        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperatures."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            _LOGGER.debug("Setting temp of %s to %s", self.unique_id, temp)
            self._api.apply_optimistic_state({"GrillSetTemp": int(temp)})
            self.async_write_ha_state()
            await self._async_execute_api_command(
                f"set grill temperature to {temp}",
                self._api.set_grill_temp,
                temp,
                debounce_key="grill_set_temp",
                debounce_delay=TEMPERATURE_COMMAND_DEBOUNCE,
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new operation mode."""
        _LOGGER.debug("Setting operation mode of %s to %s", self.unique_id, hvac_mode)

        if hvac_mode == HVACMode.HEAT:
            await self.async_turn_on()
        else:
            await self.async_turn_off()

    async def async_turn_on(self) -> None:
        """Turn on."""
        _LOGGER.debug("Turning %s on", self.unique_id)
        self._api.apply_optimistic_state({"PowerOn": True})
        self.async_write_ha_state()
        await self._async_execute_api_command(
            "turn on the grill",
            self._api.set_power_state,
            True,
        )

    async def async_turn_off(self) -> None:
        """Turn off."""
        _LOGGER.debug("Turning %s off", self.unique_id)
        self._api.apply_optimistic_state({"PowerOn": False})
        self.async_write_ha_state()
        await self._async_execute_api_command(
            "turn off the grill",
            self._api.set_power_state,
            False,
        )
