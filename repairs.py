"""Repairs and entity-id migration support for Pitboss."""

import json

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.event import async_track_device_registry_updated_event
from homeassistant.util import slugify

from .const import DEFAULT_NAME, DOMAIN

_ISSUE_ID_PREFIX = "rename_entity_ids_"
_ISSUE_TRANSLATION_KEY = "rename_entity_ids"
_SOURCE_ENTITY_IDS_KEY = "source_entity_ids"


def _issue_id(device_id: str) -> str:
    """Return the issue id for a device rename migration."""

    return f"{_ISSUE_ID_PREFIX}{device_id}"


def _effective_device_name(
    config_entry: ConfigEntry,
    *,
    name_by_user: str | None,
    name: str | None,
) -> str:
    """Return the effective Home Assistant device name."""

    return name_by_user or name or config_entry.title or DEFAULT_NAME


def _target_entity_id(domain: str, device_name: str, original_name: str) -> str:
    """Build the device-name-based entity id for an entity."""

    return f"{domain}.{slugify(f'{device_name} {original_name}')}"


def _load_source_entity_ids(data: dict[str, str]) -> list[str]:
    """Load stored source entity ids from issue data."""

    try:
        source_entity_ids = json.loads(data[_SOURCE_ENTITY_IDS_KEY])
    except KeyError, TypeError, json.JSONDecodeError:
        return []

    if not isinstance(source_entity_ids, list):
        return []

    return [entity_id for entity_id in source_entity_ids if isinstance(entity_id, str)]


@callback
def _existing_source_entity_ids(
    entity_registry: er.EntityRegistry,
    device_id: str,
    data: dict[str, str] | None,
) -> list[str]:
    """Return still-valid source entity ids already stored in an open issue."""

    if not data:
        return []

    return [
        entity_id
        for entity_id in _load_source_entity_ids(data)
        if (
            (entry := entity_registry.async_get(entity_id)) is not None
            and entry.device_id == device_id
            and entry.platform == DOMAIN
            and entry.original_name is not None
        )
    ]


def _effective_issue_old_name(data: dict[str, str] | None) -> str | None:
    """Return the original old name preserved in an existing issue."""

    if not data:
        return None

    old_name = data.get("old_name")
    return old_name if isinstance(old_name, str) and old_name else None


@callback
def _new_source_entity_ids(
    entity_registry: er.EntityRegistry,
    device_id: str,
    previous_device_name: str,
) -> list[str]:
    """Return entity ids that still match the prior device-name-based pattern."""

    source_entity_ids: list[str] = []
    for entry in er.async_entries_for_device(
        entity_registry, device_id, include_disabled_entities=True
    ):
        if entry.platform != DOMAIN or entry.original_name is None:
            continue

        if entry.entity_id != _target_entity_id(
            entry.domain, previous_device_name, entry.original_name
        ):
            continue

        source_entity_ids.append(entry.entity_id)

    source_entity_ids.sort()
    return source_entity_ids


@callback
def async_update_entity_id_rename_issue(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_id: str,
    previous_device_name: str,
) -> None:
    """Create, update, or clear the pending entity-id rename issue."""

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    issue_id = _issue_id(device_id)

    if (device := device_registry.async_get(device_id)) is None:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    current_device_name = _effective_device_name(
        config_entry,
        name_by_user=device.name_by_user,
        name=device.name,
    )
    if current_device_name == previous_device_name:
        return

    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    source_entity_ids = _existing_source_entity_ids(
        entity_registry,
        device_id,
        issue.data if issue and issue.data else None,
    )
    effective_old_name = _effective_issue_old_name(issue.data if issue else None)
    if not source_entity_ids:
        source_entity_ids = _new_source_entity_ids(
            entity_registry,
            device_id,
            previous_device_name,
        )
        effective_old_name = previous_device_name

    if not source_entity_ids:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    entity_count = str(len(source_entity_ids))
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        data={
            "device_id": device_id,
            "old_name": effective_old_name or previous_device_name,
            "new_name": current_device_name,
            "entity_count": entity_count,
            _SOURCE_ENTITY_IDS_KEY: json.dumps(source_entity_ids),
        },
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=_ISSUE_TRANSLATION_KEY,
        translation_placeholders={
            "old_name": effective_old_name or previous_device_name,
            "new_name": current_device_name,
            "entity_count": entity_count,
        },
    )


@callback
def async_track_entity_id_rename_issues(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_id: str,
):
    """Track device renames that may warrant a confirmed entity-id rename."""

    @callback
    def _async_handle_device_update(
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        if event.data["action"] != "update":
            return

        changes = event.data["changes"]
        if "name" not in changes and "name_by_user" not in changes:
            return

        device_registry = dr.async_get(hass)
        if (device := device_registry.async_get(device_id)) is None:
            ir.async_delete_issue(hass, DOMAIN, _issue_id(device_id))
            return

        previous_device_name = _effective_device_name(
            config_entry,
            name_by_user=changes.get("name_by_user", device.name_by_user),
            name=changes.get("name", device.name),
        )
        async_update_entity_id_rename_issue(
            hass,
            config_entry,
            device_id,
            previous_device_name,
        )

    return async_track_device_registry_updated_event(
        hass, device_id, _async_handle_device_update
    )


class RenameEntityIdsRepairFlow(RepairsFlow):
    """Repair flow for renaming Pit Boss entity ids after a device rename."""

    def __init__(self, data: dict[str, str]) -> None:
        """Initialize the repair flow."""

        self._device_id = data["device_id"]
        self._new_name = data["new_name"]
        self._source_entity_ids = _load_source_entity_ids(data)
        self._placeholders = {
            "old_name": data["old_name"],
            "new_name": data["new_name"],
            "entity_count": data["entity_count"],
        }

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Handle the first step of the repair flow."""

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Handle the confirmation step."""

        if user_input is not None:
            entity_registry = er.async_get(self.hass)
            rename_conflict = False
            for entity_id in self._source_entity_ids:
                if (
                    (entry := entity_registry.async_get(entity_id)) is None
                    or entry.platform != DOMAIN
                    or entry.device_id != self._device_id
                    or entry.original_name is None
                ):
                    continue

                new_entity_id = _target_entity_id(
                    entry.domain,
                    self._new_name,
                    entry.original_name,
                )
                if new_entity_id == entry.entity_id:
                    continue

                try:
                    entity_registry.async_update_entity(
                        entry.entity_id,
                        new_entity_id=new_entity_id,
                    )
                except ValueError:
                    rename_conflict = True

            if rename_conflict:
                return self.async_show_form(
                    step_id="confirm",
                    data_schema=vol.Schema({}),
                    description_placeholders=self._placeholders,
                    errors={"base": "rename_conflict"},
                )

            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders,
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str] | None,
) -> RepairsFlow:
    """Create the Pit Boss repairs flow."""

    del hass
    assert issue_id.startswith(_ISSUE_ID_PREFIX)
    assert data is not None
    return RenameEntityIdsRepairFlow(data)
