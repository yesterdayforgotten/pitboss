"""Data update coordinator for the Pitboss integration."""
import logging
from datetime import timedelta

from .pitboss_api import PitbossApi

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PitbossDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching Pitboss data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, api: PitbossApi, config: dict[str, Any]) -> None:
        """Initialize Pitboss data update coordinator."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=1),
        )
        self.api = api
        self.nickname = config.get("nickname")

    async def _async_update_data(self) -> None:
        """Update data via APIs."""
        try:
            await self.hass.async_add_executor_job(self.api.UpdateState)
        except RuntimeError as ex:
            raise UpdateFailed(
                f"Unable to refresh printer information: Printer offline: {ex}"
            ) from ex
