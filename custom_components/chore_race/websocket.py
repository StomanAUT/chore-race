"""Read-only WebSocket API for future Chore Race cards."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .errors import ChoreRaceError


def _manager(hass: HomeAssistant) -> Any:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries or entries[0].runtime_data is None:
        return None
    return entries[0].runtime_data


@websocket_api.websocket_command({vol.Required("type"): "chore_race/get_state"})
@callback
def websocket_get_state(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return compact aggregate state."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    connection.send_result(msg["id"], manager.state_snapshot())


@websocket_api.websocket_command({vol.Required("type"): "chore_race/get_tasks"})
@callback
def websocket_get_tasks(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return concrete tasks for a client-side planner/card."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    connection.send_result(
        msg["id"], [item.to_dict() for item in manager.data.tasks.values()]
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "chore_race/get_participants"}
)
@callback
def websocket_get_participants(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return participants."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    connection.send_result(
        msg["id"], [item.to_dict() for item in manager.data.participants.values()]
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "chore_race/get_chore_types"}
)
@callback
def websocket_get_chore_types(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return reusable chore types."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    connection.send_result(
        msg["id"], [item.to_dict() for item in manager.data.chore_types.values()]
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "chore_race/get_leaderboard"}
)
@callback
def websocket_get_leaderboard(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current week totals with stable participant IDs."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    totals = manager.race_points_week()
    connection.send_result(
        msg["id"],
        sorted(
            (
                {
                    "participant_id": participant.id,
                    "name": participant.name,
                    "points": totals.get(participant.id, 0),
                }
                for participant in manager.data.participants.values()
                if participant.active
            ),
            key=lambda item: (-item["points"], item["name"].casefold()),
        ),
    )


@websocket_api.websocket_command({vol.Required("type"): "chore_race/get_race_state"})
@callback
def websocket_get_race_state(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current or most recent race state."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    connection.send_result(msg["id"], manager.race_state())


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {vol.Required("type"): "chore_race/start_race"}
)
async def websocket_start_race(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Start a race from an administrator card."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    try:
        race_state = await manager.async_start_race()
    except ChoreRaceError as err:
        connection.send_error(msg["id"], "chore_race_error", str(err))
        return
    connection.send_result(msg["id"], race_state)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {vol.Required("type"): "chore_race/stop_race"}
)
async def websocket_stop_race(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stop the active race from an administrator card."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    try:
        race_state = await manager.async_stop_race()
    except ChoreRaceError as err:
        connection.send_error(msg["id"], "chore_race_error", str(err))
        return
    connection.send_result(msg["id"], race_state)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/reset_race",
        vol.Optional("race_id"): vol.All(str, vol.Length(min=1, max=64)),
    }
)
async def websocket_reset_race(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Reset one race and reopen only its completed tasks."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    try:
        race_state = await manager.async_reset_race(msg.get("race_id"))
    except ChoreRaceError as err:
        connection.send_error(msg["id"], "chore_race_error", str(err))
        return
    connection.send_result(msg["id"], race_state)


@websocket_api.require_admin
@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/remove_race_participant",
        vol.Required("participant_id"): vol.All(
            str, vol.Length(min=1, max=64)
        ),
        vol.Optional("race_id"): vol.All(str, vol.Length(min=1, max=64)),
    }
)
async def websocket_remove_race_participant(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove a participant from one race without deactivating them globally."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    try:
        race_state = await manager.async_remove_race_participant(
            msg["participant_id"], msg.get("race_id")
        )
    except ChoreRaceError as err:
        connection.send_error(msg["id"], "chore_race_error", str(err))
        return
    connection.send_result(msg["id"], race_state)


@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/complete_task",
        vol.Required("task_id"): vol.All(str, vol.Length(min=1, max=64)),
        vol.Required("participant_id"): vol.All(str, vol.Length(min=1, max=64)),
    }
)
async def websocket_complete_task(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Complete one task with the normal everyday score."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    try:
        await manager.async_complete_task(
            msg["task_id"],
            msg["participant_id"],
        )
    except ChoreRaceError as err:
        connection.send_error(msg["id"], "chore_race_error", str(err))
        return
    connection.send_result(msg["id"], manager.race_state())


@websocket_api.async_response
@websocket_api.websocket_command(
    {
        vol.Required("type"): "chore_race/complete_race_task",
        vol.Required("task_id"): vol.All(str, vol.Length(min=1, max=64)),
        vol.Required("participant_id"): vol.All(str, vol.Length(min=1, max=64)),
        vol.Optional("copilot_participant_id"): vol.All(
            str, vol.Length(min=1, max=64)
        ),
        vol.Optional("fair_play", default=False): bool,
    }
)
async def websocket_complete_race_task(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Complete one task during an active race."""
    manager = _manager(hass)
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Chore Race is not loaded")
        return
    try:
        await manager.async_complete_task(
            msg["task_id"],
            msg["participant_id"],
            require_active_race=True,
            copilot_participant_id=msg.get("copilot_participant_id"),
            fair_play=msg["fair_play"],
        )
    except ChoreRaceError as err:
        connection.send_error(msg["id"], "chore_race_error", str(err))
        return
    connection.send_result(msg["id"], manager.race_state())


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all authenticated commands once."""
    for command in (
        websocket_get_state,
        websocket_get_tasks,
        websocket_get_participants,
        websocket_get_chore_types,
        websocket_get_leaderboard,
        websocket_get_race_state,
        websocket_start_race,
        websocket_stop_race,
        websocket_reset_race,
        websocket_remove_race_participant,
        websocket_complete_task,
        websocket_complete_race_task,
    ):
        websocket_api.async_register_command(hass, command)
