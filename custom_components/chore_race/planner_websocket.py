"""Admin-only WebSocket commands for the Chore Race planner."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar

from .const import DOMAIN
from .errors import ChoreRaceError
from .manager import ChoreRaceManager
from .models import Difficulty, TaskSource

_ID = vol.All(str, vol.Length(min=1, max=64))
_NAME = vol.All(str, vol.Strip, vol.Length(min=1, max=100))
_POINTS = vol.All(int, vol.Range(min=0, max=1000))
_OPTIONAL_TEXT = vol.Any(None, vol.All(str, vol.Length(max=255)))


def _manager(hass: HomeAssistant) -> ChoreRaceManager | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries or entries[0].runtime_data is None:
        return None
    return entries[0].runtime_data


def _require_manager(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> ChoreRaceManager | None:
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
    return manager


def _send_domain_error(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    err: ChoreRaceError,
) -> None:
    connection.send_error(msg["id"], "chore_race_error", str(err))


@websocket_api.websocket_command({vol.Required("type"): "chore_race/get_areas"})
@callback
def websocket_get_areas(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current HA areas without duplicating room management."""
    registry = ar.async_get(hass)
    connection.send_result(
        msg["id"],
        sorted(
            (
                {
                    "area_id": area.id,
                    "name": area.name,
                    "icon": area.icon,
                    "picture": area.picture,
                }
                for area in registry.async_list_areas()
            ),
            key=lambda area: area["name"].casefold(),
        ),
    )


@websocket_api.websocket_command({vol.Required("type"): "chore_race/get_settings"})
@callback
def websocket_get_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return planner and race-ready settings."""
    if (manager := _require_manager(hass, connection, msg)) is not None:
        connection.send_result(msg["id"], manager.data.settings.to_dict())


@websocket_api.websocket_command(
    {vol.Required("type"): "chore_race/get_recurrence_rules"}
)
@callback
def websocket_get_recurrence_rules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return recurrence rules for the planner."""
    if (manager := _require_manager(hass, connection, msg)) is not None:
        connection.send_result(
            msg["id"], list(manager.data.recurrence_rules.values())
        )


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/create_participant",
        vol.Required("name"): _NAME,
        vol.Optional("person_entity_id"): _OPTIONAL_TEXT,
        vol.Optional("avatar"): _OPTIONAL_TEXT,
        vol.Optional("sort_order", default=0): int,
        vol.Optional("role", default="child"): vol.In(["child", "adult"]),
        vol.Optional("can_do_restricted_tasks", default=False): bool,
    }
)
async def websocket_create_participant(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create a participant from an admin planner."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    try:
        participant = await manager.async_create_participant(
            msg["name"],
            person_entity_id=msg.get("person_entity_id"),
            avatar=msg.get("avatar"),
            sort_order=msg["sort_order"],
            role=msg["role"],
            can_do_restricted_tasks=msg["can_do_restricted_tasks"],
        )
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], participant.to_dict())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/update_participant",
        vol.Required("participant_id"): _ID,
        vol.Optional("name"): _NAME,
        vol.Optional("active"): bool,
        vol.Optional("person_entity_id"): _OPTIONAL_TEXT,
        vol.Optional("avatar"): _OPTIONAL_TEXT,
        vol.Optional("sort_order"): int,
        vol.Optional("role"): vol.In(["child", "adult"]),
        vol.Optional("can_do_restricted_tasks"): bool,
    }
)
async def websocket_update_participant(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update a participant from an admin planner."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    changes = {
        key: msg[key]
        for key in (
            "name",
            "active",
            "person_entity_id",
            "avatar",
            "sort_order",
            "role",
            "can_do_restricted_tasks",
        )
        if key in msg
    }
    try:
        participant = await manager.async_update_participant(
            msg["participant_id"], **changes
        )
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], participant.to_dict())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/create_chore_type",
        vol.Required("name"): _NAME,
        vol.Required("default_race_points"): _POINTS,
        vol.Optional("icon"): _OPTIONAL_TEXT,
        vol.Optional("image"): _OPTIONAL_TEXT,
        vol.Optional("streak_enabled", default=False): bool,
        vol.Optional("streak_max_bonus", default=0): _POINTS,
        vol.Optional("default_copilot_points", default=1): _POINTS,
        vol.Optional("difficulty"): vol.Any(
            None, vol.In([item.value for item in Difficulty])
        ),
        vol.Optional("adult_only", default=False): bool,
        vol.Optional("confirmation_required", default=False): bool,
    }
)
async def websocket_create_chore_type(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create a chore type from an admin planner."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    values = {
        key: msg[key]
        for key in (
            "icon",
            "image",
            "streak_enabled",
            "streak_max_bonus",
            "default_copilot_points",
            "difficulty",
            "adult_only",
            "confirmation_required",
        )
        if key in msg
    }
    try:
        chore_type = await manager.async_create_chore_type(
            msg["name"], msg["default_race_points"], **values
        )
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], chore_type.to_dict())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/update_chore_type",
        vol.Required("chore_type_id"): _ID,
        vol.Optional("name"): _NAME,
        vol.Optional("default_race_points"): _POINTS,
        vol.Optional("icon"): _OPTIONAL_TEXT,
        vol.Optional("image"): _OPTIONAL_TEXT,
        vol.Optional("streak_enabled"): bool,
        vol.Optional("streak_max_bonus"): _POINTS,
        vol.Optional("default_copilot_points"): _POINTS,
        vol.Optional("active"): bool,
        vol.Optional("difficulty"): vol.Any(
            None, vol.In([item.value for item in Difficulty])
        ),
        vol.Optional("adult_only"): bool,
        vol.Optional("confirmation_required"): bool,
    }
)
async def websocket_update_chore_type(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update a chore type from an admin planner."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    changes = {
        key: value
        for key, value in msg.items()
        if key not in {"id", "type", "chore_type_id"}
    }
    try:
        chore_type = await manager.async_update_chore_type(
            msg["chore_type_id"], **changes
        )
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], chore_type.to_dict())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/delete_chore_type",
        vol.Required("chore_type_id"): _ID,
    }
)
async def websocket_delete_chore_type(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete an unused chore type."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    try:
        await manager.async_delete_chore_type(msg["chore_type_id"])
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], {})


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/create_task",
        vol.Required("chore_type_id"): _ID,
        vol.Required("date"): vol.Coerce(date.fromisoformat),
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("race_points"): _POINTS,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
        vol.Optional("source", default=TaskSource.MANUAL.value): vol.Coerce(
            TaskSource
        ),
        vol.Optional("source_entity_id"): _OPTIONAL_TEXT,
        vol.Optional("blocked", default=False): bool,
    }
)
async def websocket_create_task(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create a dated task from an admin planner."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    try:
        task = await manager.async_create_task(
            msg["chore_type_id"],
            msg["date"],
            area_id=msg.get("area_id"),
            race_points=msg.get("race_points"),
            preferred_participant_id=msg.get("preferred_participant_id"),
            source=msg["source"],
            source_entity_id=msg.get("source_entity_id"),
            blocked=msg["blocked"],
        )
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], task.to_dict())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/update_task",
        vol.Required("task_id"): _ID,
        vol.Optional("chore_type_id"): _ID,
        vol.Optional("date"): vol.Coerce(date.fromisoformat),
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("race_points"): _POINTS,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
        vol.Optional("blocked"): bool,
    }
)
async def websocket_update_task(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update an untouched open task."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    changes = {
        key: value
        for key, value in msg.items()
        if key not in {"id", "type", "task_id"}
    }
    try:
        task = await manager.async_update_task(msg["task_id"], **changes)
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], task.to_dict())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/delete_task",
        vol.Required("task_id"): _ID,
    }
)
async def websocket_delete_task(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete an untouched open task."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    try:
        await manager.async_delete_task(msg["task_id"])
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], {})


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/create_recurrence_rule",
        vol.Required("chore_type_id"): _ID,
        vol.Required("start_date"): vol.Coerce(date.fromisoformat),
        vol.Required("frequency"): vol.In(["days", "monthly", "yearly"]),
        vol.Optional("interval", default=1): vol.All(
            int, vol.Range(min=1, max=365)
        ),
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
    }
)
async def websocket_create_recurrence_rule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create and materialize a recurrence rule from the planner."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    try:
        rule = await manager.async_create_recurrence_rule(
            msg["chore_type_id"],
            msg["start_date"],
            frequency=msg["frequency"],
            interval=msg["interval"],
            area_id=msg.get("area_id"),
            preferred_participant_id=msg.get("preferred_participant_id"),
        )
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], rule)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/update_settings",
        vol.Optional("normal_completion_points"): _POINTS,
        vol.Optional("fair_play_bonus"): _POINTS,
        vol.Optional("race_enabled"): bool,
        vol.Optional("race_duration_seconds"): vol.All(
            int, vol.Range(min=60, max=14400)
        ),
        vol.Optional("race_weekdays"): vol.All(
            [vol.All(int, vol.Range(min=0, max=6))], vol.Length(min=1)
        ),
        vol.Optional("race_ready_time"): vol.Match(
            r"^(?:[01]\d|2[0-3]):[0-5]\d$"
        ),
    }
)
async def websocket_update_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update settings from an admin planner."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    changes = {
        key: value for key, value in msg.items() if key not in {"id", "type"}
    }
    try:
        settings = await manager.async_update_settings(**changes)
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], settings.to_dict())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/update_recurrence_rule",
        vol.Required("rule_id"): _ID,
        vol.Optional("chore_type_id"): _ID,
        vol.Optional("start_date"): vol.Coerce(date.fromisoformat),
        vol.Optional("frequency"): vol.In(["days", "monthly", "yearly"]),
        vol.Optional("interval"): vol.All(int, vol.Range(min=1, max=365)),
        vol.Optional("area_id"): _OPTIONAL_TEXT,
        vol.Optional("preferred_participant_id"): _OPTIONAL_TEXT,
        vol.Optional("active"): bool,
    }
)
async def websocket_update_recurrence_rule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update or deactivate a recurrence rule."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    changes = {
        key: value for key, value in msg.items() if key not in {"id", "type", "rule_id"}
    }
    try:
        rule = await manager.async_update_recurrence_rule(
            msg["rule_id"], **changes
        )
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], rule)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/delete_recurrence_rule",
        vol.Required("rule_id"): _ID,
    }
)
async def websocket_delete_recurrence_rule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete a recurrence rule without deleting generated tasks."""
    manager = _require_manager(hass, connection, msg)
    if manager is None:
        return
    try:
        await manager.async_delete_recurrence_rule(msg["rule_id"])
    except ChoreRaceError as err:
        _send_domain_error(connection, msg, err)
        return
    connection.send_result(msg["id"], {})


def async_register_planner_websocket_commands(hass: HomeAssistant) -> None:
    """Register read and admin-only planner commands."""
    for command in (
        websocket_get_areas,
        websocket_get_settings,
        websocket_get_recurrence_rules,
        websocket_create_participant,
        websocket_update_participant,
        websocket_create_chore_type,
        websocket_update_chore_type,
        websocket_delete_chore_type,
        websocket_create_task,
        websocket_update_task,
        websocket_delete_task,
        websocket_create_recurrence_rule,
        websocket_update_settings,
        websocket_update_recurrence_rule,
        websocket_delete_recurrence_rule,
    ):
        websocket_api.async_register_command(hass, command)
