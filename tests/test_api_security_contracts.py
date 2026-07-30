"""Permission and error contracts for the public Chore Race API."""

from __future__ import annotations

import ast
from pathlib import Path

from custom_components.chore_race.errors import (
    ChoreRaceError,
    ConflictError,
    NotFoundError,
    ValidationError,
)

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components/chore_race"


def _function_decorators(path: Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        result[node.name] = {
            ast.unparse(decorator) for decorator in node.decorator_list
        }
    return result


def _assigned_set(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
            and isinstance(node.value, ast.Set)
        ):
            return {
                item.id
                for item in node.value.elts
                if isinstance(item, ast.Name)
            }
    raise AssertionError(f"{name} is not a literal set")


def _assigned_dict_keys(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
            and isinstance(node.value, ast.Dict)
        ):
            return {
                key.id for key in node.value.keys if isinstance(key, ast.Name)
            }
    raise AssertionError(f"{name} is not a literal dict")


def test_planner_mutations_are_admin_only():
    """Every planner write must retain Home Assistant's admin guard."""
    decorators = _function_decorators(COMPONENT / "planner_websocket.py")
    mutations = {
        name
        for name in decorators
        if name.startswith(
            (
                "websocket_create_",
                "websocket_update_",
                "websocket_delete_",
            )
        )
    }

    assert mutations
    for name in mutations:
        assert "websocket_api.require_admin" in decorators[name], name


def test_race_management_is_admin_only_but_household_actions_are_not():
    """Separate administration from authenticated shared-tablet actions."""
    decorators = _function_decorators(COMPONENT / "websocket.py")
    admin_commands = {
        "websocket_start_race",
        "websocket_stop_race",
        "websocket_reset_race",
        "websocket_remove_race_participant",
    }
    household_commands = {
        "websocket_complete_task",
        "websocket_complete_race_task",
        "websocket_select_reward",
    }

    for name in admin_commands:
        assert "websocket_api.require_admin" in decorators[name], name
    for name in household_commands:
        assert "websocket_api.require_admin" not in decorators[name], name


def test_service_admin_set_covers_every_management_schema():
    """Only task completion remains callable by a non-admin user context."""
    setup = COMPONENT / "__init__.py"
    registered = _assigned_dict_keys(setup, "schemas")
    admin = _assigned_set(setup, "ADMIN_SERVICES")

    assert registered - admin == {"SERVICE_COMPLETE_TASK"}


def test_domain_error_codes_are_stable_and_specific():
    """Clients branch on codes and may display messages independently."""
    assert ChoreRaceError.code == "chore_race_error"
    assert NotFoundError.code == "not_found"
    assert ConflictError.code == "conflict"
    assert ValidationError.code == "validation_error"


def test_adapters_expose_domain_codes_to_websocket_and_service_clients():
    """Prevent adapters from collapsing typed failures into one generic code."""
    websocket_sources = (
        (COMPONENT / "websocket.py").read_text(encoding="utf-8"),
        (COMPONENT / "planner_websocket.py").read_text(encoding="utf-8"),
    )
    service_source = (COMPONENT / "__init__.py").read_text(encoding="utf-8")

    assert all(
        'connection.send_error(msg["id"], err.code, str(err))' in source
        for source in websocket_sources
    )
    assert "translation_key=err.code" in service_source
    assert "raise ServiceValidationError(" in service_source
