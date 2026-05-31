"""Config flow for Pitboss integration."""

import asyncio
from ipaddress import IPv4Network, ip_network
import logging
from typing import Any

from aiohttp import ClientError, ClientTimeout
import voluptuous as vol

from homeassistant.components.network import async_get_adapters
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    DATA_DEVICE_INFO,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DISCOVERY_PARALLELISM,
    DISCOVERY_TIMEOUT_SECONDS,
    DOMAIN,
    INFO_APP,
    INFO_MAC,
    INFO_MODEL_ID,
    SUPPORTED_MODEL_IDS,
)
from .pitboss_api import PitbossApi

_LOGGER = logging.getLogger(__name__)

CONF_SUBNET = "subnet"
DEFAULT_DISCOVERY_SUBNET = "192.168.0.0/24"
MAX_DISCOVERY_HOSTS = 256

STEP_MANUAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)

STEP_DISCOVER_SUBNET_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SUBNET, default=DEFAULT_DISCOVERY_SUBNET): str,
    }
)


def _entry_data_from_user_input(
    user_input: dict[str, Any], device_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Normalize config entry data from user input."""

    data: dict[str, Any] = {CONF_HOST: user_input[CONF_HOST]}
    if device_info is not None:
        data[DATA_DEVICE_INFO] = device_info
    return data


def _entry_title_from_device_info(device_info: dict[str, Any]) -> str:
    """Return the config entry title from device info."""

    return f"{DEFAULT_NAME} {device_info[INFO_MODEL_ID].upper()}"


def _discovery_option_label(device_info: dict[str, Any]) -> str:
    """Build the selector label for a discovered smoker."""

    app = device_info.get(INFO_APP) or "unknown"
    return f"{device_info[INFO_MODEL_ID]} | {device_info[INFO_MAC]} | {app}"


def _discovery_schema(discovered_devices: dict[str, dict[str, Any]]) -> vol.Schema:
    """Build the discovery selector schema."""

    return vol.Schema(
        {
            vol.Required(CONF_HOST): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {
                            "value": host,
                            "label": _discovery_option_label(device_info),
                        }
                        for host, device_info in discovered_devices.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


async def _async_validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
    *,
    timeout: ClientTimeout | None = None,
) -> dict[str, Any]:
    """Validate user input and return normalized device info."""

    api = PitbossApi(data[CONF_HOST], async_get_clientsession(hass))
    device_info = await api.update_device_info(timeout=timeout)
    unique_id = api.get_unique_id()
    model = api.get_model()

    if not unique_id:
        raise InvalidResponse

    if model not in SUPPORTED_MODEL_IDS:
        raise UnsupportedModel(model)

    return device_info


def _set_validate_input_error(
    err: Exception,
    errors: dict[str, str],
    description_placeholders: dict[str, str],
) -> None:
    """Map validation errors to Home Assistant config flow error keys."""
    if isinstance(err, (ClientError, asyncio.TimeoutError)):
        errors["base"] = "cannot_connect"
        return

    if isinstance(err, UnsupportedModel):
        errors["base"] = "unsupported_model"
        description_placeholders["model"] = err.model
        return

    if isinstance(err, InvalidResponse):
        errors["base"] = "unknown"
        return

    _LOGGER.exception("An unknown error has occurred")
    errors["base"] = "unknown"


async def _async_probe_discovery_host(
    hass: HomeAssistant, host: str
) -> tuple[str, dict[str, Any] | None]:
    """Probe one discovery host for Pit Boss device info."""

    try:
        device_info = await _async_validate_input(
            hass,
            {CONF_HOST: host},
            timeout=ClientTimeout(total=DISCOVERY_TIMEOUT_SECONDS),
        )
    except (
        ClientError,
        asyncio.TimeoutError,
        InvalidResponse,
        UnsupportedModel,
        ValueError,
    ):
        return host, None

    return host, device_info


async def _async_discover_supported_devices(
    hass: HomeAssistant,
    networks: list[IPv4Network] | None = None,
) -> dict[str, dict[str, Any]]:
    """Scan enabled local IPv4 /24 networks for supported Pit Boss smokers."""

    addresses: set[str] = set()
    if networks is None:
        networks = []
        for adapter in await async_get_adapters(hass):
            if not adapter["enabled"]:
                continue
            for ipv4 in adapter["ipv4"]:
                address = ipv4["address"]
                networks.append(ip_network(f"{address}/24", strict=False))

    for network in networks:
        for host in network.hosts():
            addresses.add(str(host))

    semaphore = asyncio.Semaphore(DISCOVERY_PARALLELISM)

    async def _probe(host: str) -> tuple[str, dict[str, Any] | None]:
        async with semaphore:
            return await _async_probe_discovery_host(hass, host)

    results = await asyncio.gather(*(_probe(host) for host in sorted(addresses)))
    return {
        host: device_info for host, device_info in results if device_info is not None
    }


class PitbossConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pitboss."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the Pit Boss config flow."""

        self._discovered_devices: dict[str, dict[str, Any]] = {}

    def _async_show_discover_subnet_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Show the custom subnet discovery fallback form."""

        return self.async_show_form(
            step_id="discover_subnet",
            data_schema=STEP_DISCOVER_SUBNET_SCHEMA,
            errors=errors or {},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PitbossOptionsFlow:
        """Return the options flow handler."""
        return PitbossOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the entry-point menu for setup."""

        return self.async_show_menu(
            step_id="user",
            menu_options=["discover", "manual"],
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual host entry."""

        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                device_info = await _async_validate_input(
                    self.hass, _entry_data_from_user_input(user_input)
                )
            except asyncio.CancelledError:
                raise
            except Exception as err:  # pylint: disable=broad-except
                _set_validate_input_error(err, errors, description_placeholders)
            else:
                entry_data = _entry_data_from_user_input(user_input, device_info)
                unique_id = device_info[INFO_MAC]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                self._async_abort_entries_match({CONF_HOST: entry_data[CONF_HOST]})
                return self.async_create_entry(
                    title=_entry_title_from_device_info(device_info),
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=STEP_MANUAL_DATA_SCHEMA,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle bounded IPv4 discovery for supported Pit Boss smokers."""

        if not self._discovered_devices:
            self._discovered_devices = await _async_discover_supported_devices(
                self.hass
            )
            if not self._discovered_devices:
                return self._async_show_discover_subnet_form()

        if user_input is not None:
            selected_host = user_input[CONF_HOST]
            device_info = self._discovered_devices[selected_host]
            entry_data = _entry_data_from_user_input(user_input, device_info)

            await self.async_set_unique_id(device_info[INFO_MAC])
            self._abort_if_unique_id_configured()
            self._async_abort_entries_match({CONF_HOST: selected_host})
            return self.async_create_entry(
                title=_entry_title_from_device_info(device_info),
                data=entry_data,
            )

        return self.async_show_form(
            step_id="discover",
            data_schema=_discovery_schema(self._discovered_devices),
        )

    async def async_step_discover_subnet(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle explicit subnet discovery when auto-detected networks fail."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                network = ip_network(user_input[CONF_SUBNET], strict=False)
            except ValueError:
                errors["base"] = "invalid_subnet"
            else:
                if network.version != 4:
                    errors["base"] = "invalid_subnet"
                elif network.num_addresses > MAX_DISCOVERY_HOSTS:
                    errors["base"] = "subnet_too_large"
                else:
                    self._discovered_devices = await _async_discover_supported_devices(
                        self.hass, [network]
                    )
                    if not self._discovered_devices:
                        errors["base"] = "no_devices_found"
                    else:
                        return await self.async_step_discover()

        return self._async_show_discover_subnet_form(errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration to update the smoker host address."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            try:
                device_info = await _async_validate_input(
                    self.hass, _entry_data_from_user_input(user_input)
                )
            except asyncio.CancelledError:
                raise
            except Exception as err:  # pylint: disable=broad-except
                _set_validate_input_error(err, errors, description_placeholders)
            else:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates=_entry_data_from_user_input(user_input, device_info),
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=reconfigure_entry.data[CONF_HOST]
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )


class PitbossOptionsFlow(config_entries.OptionsFlow):
    """Handle Pitboss options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                        int, vol.Range(min=5, max=300)
                    ),
                }
            ),
        )


class InvalidResponse(HomeAssistantError):
    """Error to indicate the device returned malformed or incomplete data."""


class UnsupportedModel(HomeAssistantError):
    """Error to indicate the smoker model is not supported."""

    def __init__(self, model: str) -> None:
        """Initialize the unsupported smoker model error."""

        super().__init__(model)
        self.model = model
