"""Business-rule tests for Chore Race Core."""

import asyncio
from datetime import date

import pytest

from custom_components.chore_race.errors import ConflictError, ValidationError
from custom_components.chore_race.models import ScoringMode, TaskStatus


async def _base_records(manager):
    await manager.async_load()
    participant = await manager.async_create_participant("Arthur")
    chore_type = await manager.async_create_chore_type("Aufräumen", 5)
    task = await manager.async_create_task(
        chore_type.id,
        date.today(),
        preferred_participant_id=participant.id,
    )
    return participant, chore_type, task


async def test_participant_id_survives_rename_and_deactivate(manager):
    """Participant names are presentation, never identity."""
    await manager.async_load()
    participant = await manager.async_create_participant("Arthur")
    changed = await manager.async_update_participant(
        participant.id, name="Arthur Neu", active=False
    )
    assert changed.id == participant.id
    assert changed.name == "Arthur Neu"
    assert changed.active is False


async def test_chore_type_validates_points(manager):
    """Invalid point defaults are rejected."""
    await manager.async_load()
    with pytest.raises(ValidationError):
        await manager.async_create_chore_type("Ungültig", -1)


async def test_task_snapshots_race_points(manager):
    """Changing a chore type does not rewrite existing task history."""
    _, chore_type, task = await _base_records(manager)
    await manager.async_update_chore_type(
        chore_type.id, default_race_points=10
    )
    assert task.race_points == 5


async def test_normal_completion_and_undo(manager):
    """Normal mode awards one point and audit-preserving undo removes it."""
    participant, _, task = await _base_records(manager)
    completion = await manager.async_complete_task(task.id, participant.id)

    assert completion.scoring_mode is ScoringMode.NORMAL
    assert completion.total_points_awarded == 1
    assert task.race_points == 5
    assert task.status is TaskStatus.COMPLETED
    assert manager.points_week()[participant.id] == 1
    assert manager.completed_tasks_today() == 1

    await manager.async_undo_completion(completion.id)

    assert completion.active is False
    assert task.status is TaskStatus.OPEN
    assert manager.points_week()[participant.id] == 0
    assert manager.completed_tasks_today() == 0


async def test_concurrent_completion_counts_once(manager):
    """Only one near-simultaneous tablet completion can win."""
    participant, _, task = await _base_records(manager)
    results = await asyncio.gather(
        manager.async_complete_task(task.id, participant.id),
        manager.async_complete_task(task.id, participant.id),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, ConflictError) for item in results) == 1
    assert manager.points_week()[participant.id] == 1


async def test_team_progress_counts_tasks_not_race_points(manager):
    """A ten-point task still counts as exactly one team completion."""
    await manager.async_load()
    participant = await manager.async_create_participant("Viktoria")
    chore_type = await manager.async_create_chore_type("WC reinigen", 10)
    task = await manager.async_create_task(
        chore_type.id, manager.today(), race_points=10
    )
    await manager.async_complete_task(task.id, participant.id)
    snapshot = manager.state_snapshot()
    assert snapshot["team_progress"] == {"completed": 1, "total": 1}
    assert snapshot["points_today"][participant.id] == 1
