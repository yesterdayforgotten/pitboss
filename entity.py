"""Entity representing a Pitboss smoker."""

from .pitboss_api import PitbossApi

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback

from .const import DOMAIN
from .coordinator import PitbossDataUpdateCoordinator

ENTITY_ID_FORMAT = DOMAIN + ".{}"


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
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        # self.entity_id = async_generate_entity_id(
        #    ENTITY_ID_FORMAT, f"{device_id}_{description.key}", hass=coordinator.hass
        # )
        # self._attr_name = {description.key}
        # self.entity_id = f"sensor.{device_id}_{description.key}"

        # self._device_id = device_id
        self._update_attr()

    @callback
    def _update_attr(self) -> None:
        """Update the state and attributes."""

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attr()
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Pitboss smoker."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._api.GetUniqueID())},
            manufacturer="Pitboss",
            # model=self._api.get_model(),
            name=self.coordinator.nickname,
            # sw_version=self._api.get_firmware_version(),
        )

    @property
    def _api(self) -> PitbossApi:
        """Return to api from coordinator."""
        return self.coordinator.api
