"""Config flow for Pitboss integration."""
from __future__ import annotations

import logging
from typing import Any

from .pitboss_api import PitbossApi
from requests.exceptions import ConnectTimeout, HTTPError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
import requests

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Required("nickname", default="PitBoss"): str,
    }
)


class PitbossConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pitboss."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                api = await self.hass.async_add_executor_job(PitbossApi, user_input['host'])
                await self.hass.async_add_executor_job(api.UpdateUniqueID)
                unique_id = api.GetUniqueID()
            except (ConnectTimeout, HTTPError):
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("An unknown error has occurred")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input["nickname"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""
    # TODO Check if there are any devices that can be discovered in the network.
    # devices = await hass.async_add_executor_job(my_pypi_dependency.discover)
    # return len(devices) > 0
    return False


# config_entry_flow.register_discovery_flow(
#    DOMAIN, "Pitboss", _async_has_devices)
