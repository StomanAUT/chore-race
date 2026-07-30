"""Chore Race integration setup."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_COMPLETE_TASK,
    SERVICE_CREATE_CHORE_TYPE,
    SERVICE_CREATE_PARTICIPANT,
    SERVICE_CREATE_RECURRENCE_RULE,
    SERVICE_CREATE_TASK,
    SERVICE_DELETE_CHORE_TYPE,
    SERVICE_DELETE_RECURRENCE_RULE,
    SERVICE_DELETE_TASK,
    SERVICE_ENSURE_TASK,
    SERVICE_REMOVE_RACE_PARTICIPANT,
    SERVICE_RESET_RACE,
    SERVICE_START_RACE,
    SERVICE_STOP_RACE,
    SERVICE_UNDO_COMPLETION,
    SERVICE_UPDATE_CHORE_TYPE,
    SERVICE_UPDATE_PARTICIPANT,
    SERVICE_UPDATE_RECURRENCE_RULE,
    SERVICE_UPDATE_TASK,
)
from .errors import ChoreRaceError
from .manager import ChoreRaceManager
from .models import Difficulty, TaskSource
from .planner_websocket import async_register_planner_websocket_commands
from .storage import ChoreRaceStore
from .websocket import async_register_websocket_commands

type ChoreRaceConfigEntry = ConfigEntry[ChoreRaceManager]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
ASSET_URL = "/chore-race-assets"
ASSET_PATH = Path(__file__).parent / "task_icons"

_ID = vol.All(str, vol.Length(min=1, max=64))
_NAME = vol.All(str, vol.Strip, vol.Length(min=1, max=100))
_POINTS = vol.All(vol.Coerce(int), vol.Range(min=0, max=1000))
_OPTIONAL_TEXT = vol.Any(None, vol.All(str, vol.Length(max=255)))

CREATE_PARTICIPANT_SCHEMA = vol.Schema(
    {
        vol.Required("name"): _NAME,
        vol.Optional("person_entity_id"): _OPTIONAL_TEXT,
        vol.Optional("avatar"): _OPTIONAL_TEXT,
        vol.Optional("sort_order", default=0): vol.Coerce(int),
        vol.Optional("role", default="child"): vol.In(["child", "adult"]),
        vol.Optional("can_do_restricted_tasks", default=False): cv.boolean,
    }
)
UPDATE_PARTICIPANT_SCHEMA = vol.Schema(
    {
        vol.Required("participant_id"): _ID,
        vol.Optional("name"): _NAME,
        vol.Optional("active"): cv.boolean,
        vol.Optional("person_entity_id"): _OPTIONAL_TEXT,
        vol.Optional("avatar"): _OPTIONAL_TEXT,
        vol.Optional("sort_order"): vol.Coerce(int),
        vol.Optional("role"): vol.In(["child", "adult"]),
        vol.Optional("can_do_restricted_tasks"): cv.boolean,
    }
)
CREATE_CHORE_TYPE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): _NAME,
        vol.Required("default_race_points"): _POINTS,
        vol.Optional("icon"): _OPTIONAL_TEXT,
        vol.Optional("image"): _OPTIONAL_TEXT,
        vol.Optional("streak_enabled", default=False): cv.boolean,
        vol.Optional("streak_max_bonus", default=0): _POINTS,
        vol.Optional("default_copilot_points", default=1): _POINTS,
        vol.Optional("difficulty"): vol.Any(
            None, vol.In([item.value for item in Difficulty])
        ),
        vol.Optional("adult_only", default=False): cv.boolean,
        vol.Optional("confirmation_required", default=False): cv.boolean,
    }
)
UPDATE_CHORE_TYPE_SCHEMA = vol.Schema(
    {
        vol.Required("chore_type_id"): _ID,
        vol.Optional("name"): _NAME,
        vol.Optional("default_race_points"): _POINTS,
        vol.Optional("icon"): _OPTIONAL_TEXT,
        vol.Optional("image"): _OPTIONAL_TEXT,
        vol.Optional("streak_enabled"): cv.boolean,
        vol.Optional("streak_max_bonus"): _POINTS,
        vol.Optional("default_copilot_points"): _POINTS,
        vol.Optional("active"): cv.boolean,
        vol.Optional("difficulty"): vol.Any(
            None, vol.In([item.value for item in Difficulty])
        ),
        vol.Optional("adult_only"): cv.boolean,
        vol.Optional("confirmation_required"): cv.boolean,
    }
)
DELETE_CHORE_TYPE_SCHEMA = vol.Schema(
    {vol.Required("chore_type_id"): _ID}
)
CREATE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("chore_type_id"): _ID,
        vol.Required("date"): cv.date,
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("floor_id"): _OPTIONAL_TEXT,
        vol.Optional("race_points"): _POINTS,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
        vol.Optional("source", default=TaskSource.MANUAL.value): vol.In(
            [item.value for item in TaskSource]
        ),
        vol.Optional("source_entity_id"): _OPTIONAL_TEXT,
        vol.Optional("chain_id"): _OPTIONAL_TEXT,
        vol.Optional("chain_step_id"): _OPTIONAL_TEXT,
        vol.Optional("blocked", default=False): cv.boolean,
    }
)
ENSURE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("chore_type_id"): _ID,
        vol.Optional("date"): cv.date,
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("floor_id"): _OPTIONAL_TEXT,
        vol.Optional("race_points"): _POINTS,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
        vol.Optional(
            "source", default=TaskSource.AUTOMATION.value
        ): vol.In([TaskSource.ENTITY.value, TaskSource.AUTOMATION.value]),
        vol.Required("source_entity_id"): cv.entity_id,
        vol.Optional("deduplication_key"): _OPTIONAL_TEXT,
    }
)
CREATE_RECURRENCE_RULE_SCHEMA = vol.Schema(
    {
        vol.Required("chore_type_id"): _ID,
        vol.Required("start_date"): cv.date,
        vol.Required("frequency"): vol.In(
            ["days", "weekdays", "monthly", "yearly", "completion_interval"]
        ),
        vol.Optional("interval", default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
        vol.Optional("weekdays", default=[]): vol.All(
            [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
            vol.Length(max=7),
        ),
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("floor_id"): _OPTIONAL_TEXT,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
    }
)
UPDATE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("task_id"): _ID,
        vol.Optional("chore_type_id"): _ID,
        vol.Optional("date"): cv.date,
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("floor_id"): _OPTIONAL_TEXT,
        vol.Optional("race_points"): _POINTS,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
        vol.Optional("blocked"): cv.boolean,
    }
)
UPDATE_RECURRENCE_RULE_SCHEMA = vol.Schema(
    {
        vol.Required("rule_id"): _ID,
        vol.Optional("chore_type_id"): _ID,
        vol.Optional("start_date"): cv.date,
        vol.Optional("frequency"): vol.In(
            ["days", "weekdays", "monthly", "yearly", "completion_interval"]
        ),
        vol.Optional("interval"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
        vol.Optional("weekdays"): vol.All(
            [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
            vol.Length(max=7),
        ),
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("floor_id"): _OPTIONAL_TEXT,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
        vol.Optional("active"): cv.boolean,
    }
)
DELETE_RECURRENCE_RULE_SCHEMA = vol.Schema({vol.Required("rule_id"): _ID})
START_RACE_SCHEMA = vol.Schema({})
STOP_RACE_SCHEMA = vol.Schema({})
RESET_RACE_SCHEMA = vol.Schema({vol.Optional("race_id"): _ID})
REMOVE_RACE_PARTICIPANT_SCHEMA = vol.Schema(
    {
        vol.Required("participant_id"): _ID,
        vol.Optional("race_id"): _ID,
    }
)
COMPLETE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("task_id"): _ID,
        vol.Required("participant_id"): _ID,
        vol.Optional("copilot_participant_id"): _ID,
        vol.Optional("fair_play", default=False): cv.boolean,
    }
)
UNDO_COMPLETION_SCHEMA = vol.Schema({vol.Required("completion_id"): _ID})
DELETE_TASK_SCHEMA = vol.Schema({vol.Required("task_id"): _ID})

ADMIN_SERVICES = {
    SERVICE_CREATE_PARTICIPANT,
    SERVICE_UPDATE_PARTICIPANT,
    SERVICE_CREATE_CHORE_TYPE,
    SERVICE_UPDATE_CHORE_TYPE,
    SERVICE_DELETE_CHORE_TYPE,
    SERVICE_CREATE_TASK,
    SERVICE_ENSURE_TASK,
    SERVICE_UPDATE_TASK,
    SERVICE_CREATE_RECURRENCE_RULE,
    SERVICE_UPDATE_RECURRENCE_RULE,
    SERVICE_DELETE_RECURRENCE_RULE,
    SERVICE_START_RACE,
    SERVICE_STOP_RACE,
    SERVICE_RESET_RACE,
    SERVICE_REMOVE_RACE_PARTICIPANT,
    SERVICE_UNDO_COMPLETION,
    SERVICE_DELETE_TASK,
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions and WebSocket commands independent of entry load."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(ASSET_URL, str(ASSET_PATH), cache_headers=True)]
    )
    async_register_websocket_commands(hass)
    async_register_planner_websocket_commands(hass)

    async def handle_service(call: ServiceCall) -> dict[str, Any] | None:
        manager = _get_manager(hass)
        if call.service in ADMIN_SERVICES:
            await _async_require_admin(hass, call)
        values = dict(call.data)
        try:
            if call.service == SERVICE_CREATE_PARTICIPANT:
                result = await manager.async_create_participant(**values)
            elif call.service == SERVICE_UPDATE_PARTICIPANT:
                record_id = values.pop("participant_id")
                result = await manager.async_update_participant(record_id, **values)
            elif call.service == SERVICE_CREATE_CHORE_TYPE:
                result = await manager.async_create_chore_type(**values)
            elif call.service == SERVICE_UPDATE_CHORE_TYPE:
                record_id = values.pop("chore_type_id")
                result = await manager.async_update_chore_type(record_id, **values)
            elif call.service == SERVICE_DELETE_CHORE_TYPE:
                await manager.async_delete_chore_type(**values)
                return {} if call.return_response else None
            elif call.service == SERVICE_CREATE_TASK:
                task_date: date = values.pop("date")
                result = await manager.async_create_task(
                    task_date=task_date, **values
                )
            elif call.service == SERVICE_ENSURE_TASK:
                task_date = values.pop("date", manager.today())
                result = await manager.async_ensure_task(
                    task_date=task_date, **values
                )
            elif call.service == SERVICE_UPDATE_TASK:
                record_id = values.pop("task_id")
                result = await manager.async_update_task(record_id, **values)
            elif call.service == SERVICE_CREATE_RECURRENCE_RULE:
                start_date: date = values.pop("start_date")
                result = await manager.async_create_recurrence_rule(
                    start_date=start_date, **values
                )
            elif call.service == SERVICE_UPDATE_RECURRENCE_RULE:
                rule_id = values.pop("rule_id")
                result = await manager.async_update_recurrence_rule(
                    rule_id, **values
                )
            elif call.service == SERVICE_DELETE_RECURRENCE_RULE:
                await manager.async_delete_recurrence_rule(**values)
                return {} if call.return_response else None
            elif call.service == SERVICE_START_RACE:
                result = await manager.async_start_race()
            elif call.service == SERVICE_STOP_RACE:
                result = await manager.async_stop_race()
            elif call.service == SERVICE_RESET_RACE:
                result = await manager.async_reset_race(**values)
            elif call.service == SERVICE_REMOVE_RACE_PARTICIPANT:
                result = await manager.async_remove_race_participant(**values)
            elif call.service == SERVICE_COMPLETE_TASK:
                result = await manager.async_complete_task(**values)
            elif call.service == SERVICE_UNDO_COMPLETION:
                result = await manager.async_undo_completion(**values)
            elif call.service == SERVICE_DELETE_TASK:
                await manager.async_delete_task(**values)
                return {} if call.return_response else None
            else:
                raise HomeAssistantError("Unknown Chore Race action")
        except ChoreRaceError as err:
            raise HomeAssistantError(str(err)) from err
        if not call.return_response:
            return None
        return result if isinstance(result, dict) else result.to_dict()

    schemas = {
        SERVICE_CREATE_PARTICIPANT: CREATE_PARTICIPANT_SCHEMA,
        SERVICE_UPDATE_PARTICIPANT: UPDATE_PARTICIPANT_SCHEMA,
        SERVICE_CREATE_CHORE_TYPE: CREATE_CHORE_TYPE_SCHEMA,
        SERVICE_UPDATE_CHORE_TYPE: UPDATE_CHORE_TYPE_SCHEMA,
        SERVICE_DELETE_CHORE_TYPE: DELETE_CHORE_TYPE_SCHEMA,
        SERVICE_CREATE_TASK: CREATE_TASK_SCHEMA,
        SERVICE_ENSURE_TASK: ENSURE_TASK_SCHEMA,
        SERVICE_UPDATE_TASK: UPDATE_TASK_SCHEMA,
        SERVICE_CREATE_RECURRENCE_RULE: CREATE_RECURRENCE_RULE_SCHEMA,
        SERVICE_UPDATE_RECURRENCE_RULE: UPDATE_RECURRENCE_RULE_SCHEMA,
        SERVICE_DELETE_RECURRENCE_RULE: DELETE_RECURRENCE_RULE_SCHEMA,
        SERVICE_START_RACE: START_RACE_SCHEMA,
        SERVICE_STOP_RACE: STOP_RACE_SCHEMA,
        SERVICE_RESET_RACE: RESET_RACE_SCHEMA,
        SERVICE_REMOVE_RACE_PARTICIPANT: REMOVE_RACE_PARTICIPANT_SCHEMA,
        SERVICE_COMPLETE_TASK: COMPLETE_TASK_SCHEMA,
        SERVICE_UNDO_COMPLETION: UNDO_COMPLETION_SCHEMA,
        SERVICE_DELETE_TASK: DELETE_TASK_SCHEMA,
    }
    for name, schema in schemas.items():
        hass.services.async_register(
            DOMAIN,
            name,
            handle_service,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ChoreRaceConfigEntry
) -> bool:
    """Load one Chore Race config entry."""
    manager = ChoreRaceManager(hass, ChoreRaceStore(hass))
    await manager.async_load()
    await manager.async_materialize_recurrences()

    async def materialize_recurring_tasks(now: Any) -> None:
        await manager.async_materialize_recurrences(now.date())

    manager.remove_recurrence_listener = async_track_time_change(
        hass,
        materialize_recurring_tasks,
        hour=0,
        minute=5,
        second=0,
    )
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ChoreRaceConfigEntry
) -> bool:
    """Unload entities and release runtime data."""
    remove_listener = getattr(
        entry.runtime_data, "remove_recurrence_listener", None
    )
    if remove_listener:
        remove_listener()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _get_manager(hass: HomeAssistant) -> ChoreRaceManager:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries or entries[0].runtime_data is None:
        raise HomeAssistantError("Chore Race is not configured or loaded")
    return entries[0].runtime_data


async def _async_require_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Require HA admin for interactive management actions.

    Calls without a user context are trusted HA automations.
    """
    if call.context.user_id is None:
        return
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None or not user.is_admin:
        raise Unauthorized(context=call.context)
