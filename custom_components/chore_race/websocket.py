"""Read-only WebSocket API for future Chore Race cards."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


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
    totals = manager.points_week()
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


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all authenticated commands once."""
    for command in (
        websocket_get_state,
        websocket_get_tasks,
        websocket_get_participants,
        websocket_get_chore_types,
        websocket_get_leaderboard,
    ):
        websocket_api.async_register_command(hass, command)
