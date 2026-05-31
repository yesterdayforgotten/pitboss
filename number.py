"""Number platform for the Pit Boss integration."""

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter

from . import PitbossConfigEntry
from .const import TEMPERATURE_COMMAND_DEBOUNCE
from .entity import PitbossEntity

_PROBE_TARGET_MIN_F = 130
_PROBE_TARGET_MAX_F = 400


def _probe_target_limit_in_native_unit(is_fahrenheit: bool, value_f: int) -> float:
    """Return a probe target limit in the active temperature unit."""
    if is_fahrenheit:
        return float(value_f)

    return TemperatureConverter.convert(
        value_f,
        UnitOfTemperature.FAHRENHEIT,
        UnitOfTemperature.CELSIUS,
    )


class _PitbossTemperatureUnitMixin:
    """Shared temperature unit and bounds behavior for Pit Boss number entities."""

    @property
    def _is_fahrenheit(self) -> bool:
        """Return True when the smoker reports Fahrenheit mode."""
        return self._api.is_fahrenheit()

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        if not self._is_fahrenheit:
            return UnitOfTemperature.CELSIUS

        return UnitOfTemperature.FAHRENHEIT

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        return _probe_target_limit_in_native_unit(
            self._is_fahrenheit, _PROBE_TARGET_MIN_F
        )

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        return _probe_target_limit_in_native_unit(
            self._is_fahrenheit, _PROBE_TARGET_MAX_F
        )


class PitbossProbeTargetNumber(
    _PitbossTemperatureUnitMixin, PitbossEntity, NumberEntity
):
    """Writable probe target temperature setpoint."""

    entity_description: NumberEntityDescription

    _attr_icon = "mdi:thermometer-lines"
    _attr_native_step = 10
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> float:
        """Return the current probe target temperature."""
        return float(self._api.get_state_value("P1SetTemp"))

    async def async_set_native_value(self, value: float) -> None:
        """Set a new probe target temperature."""
        self._api.apply_optimistic_state({"P1SetTemp": int(value)})
        self.coordinator.update_probe_target_reached_times()
        await self._async_execute_api_command(
            f"set probe target temperature to {value}",
            self._api.set_probe1_temp,
            value,
            debounce_key="probe1_set_temp",
            debounce_delay=TEMPERATURE_COMMAND_DEBOUNCE,
        )


class PitbossVirtualProbeTargetNumber(
    _PitbossTemperatureUnitMixin, PitbossEntity, RestoreNumber
):
    """Local-only target temperature setpoint for Probe 2."""

    entity_description: NumberEntityDescription

    _attr_icon = "mdi:thermometer-lines"
    _attr_native_step = 10
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _target_key = "P2SetTemp"
    _attr_native_value: float = 0.0

    @property
    def available(self) -> bool:
        """Keep the local target editable even if the smoker is offline."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last configured target when Home Assistant starts."""
        await super().async_added_to_hass()
        if (
            last_number_data := await self.async_get_last_number_data()
        ) is not None and (last_number_data.native_value is not None):
            self._attr_native_value = last_number_data.native_value
            self.coordinator.set_virtual_probe_target(
                self._target_key, int(last_number_data.native_value)
            )

    @property
    def native_value(self) -> float:
        """Return the locally stored target temperature."""
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Store a new local target temperature."""
        rounded_value = float(int(value))
        self._attr_native_value = rounded_value
        self.coordinator.set_virtual_probe_target(self._target_key, int(rounded_value))
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PitbossConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Pit Boss number entities."""
    coordinator = config_entry.runtime_data
    device_id = config_entry.unique_id or config_entry.entry_id

    async_add_entities(
        [
            PitbossProbeTargetNumber(
                coordinator,
                device_id,
                NumberEntityDescription(
                    key="probe1_target_temp",
                    translation_key="probe1_target_temp",
                ),
            ),
            PitbossVirtualProbeTargetNumber(
                coordinator,
                device_id,
                NumberEntityDescription(
                    key="probe2_target_temp",
                    translation_key="probe2_target_temp",
                ),
            ),
        ]
    )
