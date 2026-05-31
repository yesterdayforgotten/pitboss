"""Support for Pitboss switches."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PitbossConfigEntry
from .entity import PitbossEntity
from .pitboss_api import PitbossApi

type OptimisticState = dict[str, bool | int | float | str | None]


@dataclass(frozen=True, kw_only=True)
class PitbossSwitchEntityMixin:
    """Mixin for Pitboss switch."""

    is_on_fn: Callable[[PitbossApi, str], bool]
    turn_on_fn: Callable[[PitbossApi], Awaitable[None]]
    turn_off_fn: Callable[[PitbossApi], Awaitable[None]]
    api_key: str | None = None


@dataclass(frozen=True, kw_only=True)
class PitbossSwitchEntityDescription(SwitchEntityDescription, PitbossSwitchEntityMixin):
    """Describes a Pitboss switch."""

    available_fn: Callable[[PitbossApi, str], bool] = lambda api, _: True
    optimistic_on_state: OptimisticState = field(default_factory=dict)
    optimistic_off_state: OptimisticState = field(default_factory=dict)


SWITCHES: tuple[PitbossSwitchEntityDescription, ...] = (
    PitbossSwitchEntityDescription(
        key="primer",
        translation_key="primer",
        api_key="Priming",
        icon="mdi:motion",
        is_on_fn=lambda api, api_key: api.get_state_value(api_key),
        turn_on_fn=lambda api: api.set_prime_state(True),
        turn_off_fn=lambda api: api.set_prime_state(False),
        optimistic_on_state={"Priming": True},
        optimistic_off_state={"Priming": False},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: PitbossConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Pitboss switches."""
    coordinator = config_entry.runtime_data
    device_id = config_entry.unique_id or config_entry.entry_id

    async_add_entities(
        PitbossSwitch(coordinator, device_id, description) for description in SWITCHES
    )


class PitbossSwitch(PitbossEntity, SwitchEntity):
    """Representation of a Pitboss switch."""

    entity_description: PitbossSwitchEntityDescription

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        key = self.entity_description.api_key or self.entity_description.key
        return super().available and self.entity_description.available_fn(
            self._api, key
        )

    @property
    def is_on(self) -> bool:
        """Return the sensor state."""
        key = self.entity_description.api_key or self.entity_description.key
        return bool(self.entity_description.is_on_fn(self._api, key))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self._async_execute_api_command(
            f"turn off {self.entity_description.key}",
            self.entity_description.turn_off_fn,
            self._api,
        )
        if self.entity_description.optimistic_off_state:
            self._api.apply_optimistic_state(
                self.entity_description.optimistic_off_state
            )
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self._async_execute_api_command(
            f"turn on {self.entity_description.key}",
            self.entity_description.turn_on_fn,
            self._api,
        )
        if self.entity_description.optimistic_on_state:
            self._api.apply_optimistic_state(
                self.entity_description.optimistic_on_state
            )
            self.async_write_ha_state()
