"""Static contracts between the Lovelace cards and WebSocket adapters."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _websocket_commands() -> list[str]:
    sources = (
        ROOT / "custom_components/chore_race/websocket.py",
        ROOT / "custom_components/chore_race/planner_websocket.py",
    )
    return [
        command
        for source in sources
        for command in re.findall(
            r'vol\.Required\("type"\): "chore_race/([^"]+)"',
            source.read_text(encoding="utf-8"),
        )
    ]


def test_websocket_command_types_are_registered_once():
    """Avoid ambiguous adapters silently replacing each other at startup."""
    commands = _websocket_commands()
    assert len(commands) == len(set(commands))


def test_planner_mutations_use_registered_websocket_commands():
    """Keep the planner independent from optional HA service registration."""
    frontend = (
        ROOT / "frontend/chore-race-planner-card.js"
    ).read_text(encoding="utf-8")
    mutations = set(
        re.findall(r'this\._submit\(\s*"([^"]+)"', frontend)
    )

    assert 'callService("chore_race"' not in frontend
    assert mutations <= set(_websocket_commands())


def test_race_card_uses_registered_completion_commands():
    """Support both everyday and active-race task completion."""
    frontend = (ROOT / "frontend/chore-race-card.js").read_text(encoding="utf-8")
    completion_commands = {
        "complete_task",
        "complete_race_task",
    }

    assert {
        f'chore_race/{command}' for command in completion_commands
    } <= set(re.findall(r'"(chore_race/[^"]+)"', frontend))
    assert completion_commands <= set(_websocket_commands())
