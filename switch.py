"""Support for monitoring Pitboss sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .pitboss_api import PitbossApi
from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .entity import PitbossEntity


@dataclass
class PitbossSwitchEntityMixin:
    """Mixin for Pitboss switch."""

    is_on_fn: Callable[[PitbossApi, str], StateType | datetime]
    turn_on_fn: Callable[[PitbossApi, str], StateType | datetime]
    turn_off_fn: Callable[[PitbossApi, str], StateType | datetime]


@dataclass
class PitbossSwitchEntityDescription(
    SwitchEntityDescription, PitbossSwitchEntityMixin
):
    """Describes a Pitboss switch."""

    available_fn: Callable[[PitbossApi, str], bool] = lambda api, _: True


SWITCHES: tuple[PitbossSwitchEntityDescription, ...] = (
    PitbossSwitchEntityDescription(
        key="primer",
        translation_key="primer",
        icon="mdi:motion",
        is_on_fn=lambda api,    _: api.GetStateValue('Priming'),
        turn_on_fn=lambda api,  _: api.SetPrimeState(True),
        turn_off_fn=lambda api, _: api.SetPrimeState(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Pitboss switches."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        PitbossSwitch(coordinator, config_entry.unique_id, description) for description in SWITCHES
    )


class PitbossSwitch(PitbossEntity, SwitchEntity):
    """Representation of a Pitboss switch."""

    entity_description: PitbossSwitchEntityDescription

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return super().available and self.entity_description.available_fn(
            self._api, self.entity_description.key
        )

    @property
    def is_on(self) -> bool:
        """Return the sensor state."""
        return self.entity_description.is_on_fn(self._api, self.entity_description.key)

    def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        self.entity_description.turn_off_fn(
            self._api, self.entity_description.key)

    def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        self.entity_description.turn_on_fn(
            self._api, self.entity_description.key)
