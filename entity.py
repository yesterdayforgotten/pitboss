"""Entity representing a Pitboss smoker."""

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from aiohttp import ClientError

from homeassistant.const import CONF_HOST
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.event import async_call_later
from homeassistant.core import HassJob
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_DEVICE_INFO,
    DEFAULT_NAME,
    DOMAIN,
    INFO_FW_VERSION,
    INFO_MAC,
    INFO_MG_VERSION,
    INFO_MODEL_ID,
)
from .coordinator import PitbossDataUpdateCoordinator
from .pitboss_api import PitbossApi

_LOGGER = logging.getLogger(__name__)


class PitbossEntity(CoordinatorEntity[PitbossDataUpdateCoordinator]):
    """Defines a Pitboss device entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PitbossDataUpdateCoordinator,
        device_id: str,
        description: EntityDescription,
    ) -> None:
        """Initialize the base device entity."""
        self.entity_description = description
        super().__init__(coordinator)
        device_info = coordinator.config_entry.data.get(DATA_DEVICE_INFO, {})
        host = coordinator.config_entry.data.get(CONF_HOST)
        mac_address = device_info.get(INFO_MAC)
        registry_device_id = mac_address or device_id
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, registry_device_id)},
            manufacturer="Pit Boss",
            model=device_info.get(INFO_MODEL_ID),
            model_id=device_info.get(INFO_MODEL_ID),
            serial_number=mac_address,
            sw_version=device_info.get(INFO_FW_VERSION),
            hw_version=device_info.get(INFO_MG_VERSION),
            configuration_url=None if host is None else f"http://{host}",
        )
        if mac_address:
            self._attr_device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, mac_address)
            }
            self._attr_device_info["name"] = mac_address.upper()

    def _device_name_for_entity_id(self) -> str:
        """Return the device name to use for entity ids."""

        if mac_address := self.coordinator.config_entry.data.get(
            DATA_DEVICE_INFO, {}
        ).get(INFO_MAC):
            default_device_name = mac_address.upper()
        else:
            default_device_name = self.coordinator.config_entry.title or DEFAULT_NAME

        if (device := getattr(self, "device_entry", None)) is not None:
            return device.name_by_user or device.name or default_device_name

        return default_device_name

    @property
    def internal_integration_suggested_object_id(self) -> str | None:
        """Return a device-name-based object id without area prefixes."""

        name = self.name
        if name in (None, UNDEFINED):
            return None

        return f"{self._device_name_for_entity_id()} {name}"

    @property
    def _api(self) -> PitbossApi:
        """Return to api from coordinator."""
        return self.coordinator.api

    async def _async_perform_api_command(
        self,
        action: str,
        command: Callable[..., Awaitable[None]],
        *args: Any,
    ) -> None:
        """Run one API command under the shared write lock."""

        try:
            await self.coordinator.async_run_serialized_command(lambda: command(*args))
        except (ClientError, TimeoutError) as ex:
            raise HomeAssistantError(
                f"Failed to {action}: the Pit Boss device is unreachable"
            ) from ex
        except ValueError as ex:
            raise HomeAssistantError(
                f"Failed to {action}: the Pit Boss device returned invalid data"
            ) from ex

    def _handle_successful_command(self) -> None:
        """Reset polling and schedule a delayed confirmation refresh."""

        self.coordinator.reset_update_interval()
        async_call_later(
            self.hass,
            3,
            HassJob(self.coordinator.async_request_refresh),
        )

    async def _async_run_debounced_api_command(
        self,
        action: str,
        command: Callable[..., Awaitable[None]],
        *args: Any,
    ) -> None:
        """Execute a debounced API command and log failures."""

        try:
            await self._async_perform_api_command(action, command, *args)
        except HomeAssistantError as ex:
            _LOGGER.warning("%s", ex)
            await self.coordinator.async_request_refresh()
            return

        self._handle_successful_command()

    async def _async_execute_api_command(
        self,
        action: str,
        command: Callable[..., Awaitable[None]],
        *args: Any,
        debounce_key: str | None = None,
        debounce_delay: float = 0,
    ) -> None:
        """Execute an API command and convert low-level errors to user-facing ones."""

        if debounce_key is not None:
            self.coordinator.reset_update_interval()
            self.coordinator.async_schedule_debounced_command(
                debounce_key,
                debounce_delay,
                lambda: self._async_run_debounced_api_command(action, command, *args),
            )
            return

        await self.coordinator.async_flush_debounced_commands()
        await self._async_perform_api_command(action, command, *args)
        self._handle_successful_command()
