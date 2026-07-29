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


async def test_planner_settings_are_validated_and_persisted(manager):
    """Planner settings are centralized instead of hard coded in the UI."""
    await manager.async_load()
    settings = await manager.async_update_settings(
        race_enabled=False,
        race_duration_seconds=2700,
        race_weekdays=[4, 0, 2, 2],
        race_ready_time="18:45",
    )
    assert settings.race_enabled is False
    assert settings.race_duration_seconds == 2700
    assert settings.race_weekdays == [0, 2, 4]
    assert settings.race_ready_time == "18:45"

    with pytest.raises(ValidationError):
        await manager.async_update_settings(race_ready_time="25:99")


async def test_recurring_tasks_materialize_once_per_due_date(manager):
    """Every-N-days rules create one stable task for each due date."""
    await manager.async_load()
    participant = await manager.async_create_participant("Arthur")
    chore_type = await manager.async_create_chore_type("Müll", 3)
    start = date(2027, 7, 1)
    rule = await manager.async_create_recurrence_rule(
        chore_type.id,
        start,
        frequency="days",
        interval=2,
        preferred_participant_id=participant.id,
    )

    assert await manager.async_materialize_recurrences(date(2027, 7, 2)) == 0
    assert await manager.async_materialize_recurrences(date(2027, 7, 3)) == 1
    assert await manager.async_materialize_recurrences(date(2027, 7, 3)) == 0
    tasks = [
        task
        for task in manager.data.tasks.values()
        if task.source_entity_id == f"recurrence:{rule['id']}"
    ]
    assert len(tasks) == 1
    assert tasks[0].date == date(2027, 7, 3)


async def test_monthly_rule_uses_last_day_for_short_month(manager):
    """A rule starting on day 31 remains due in shorter months."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Monatscheck", 4)
    rule = await manager.async_create_recurrence_rule(
        chore_type.id,
        date(2027, 1, 31),
        frequency="monthly",
    )

    assert manager._rule_is_due(rule, date(2027, 2, 28))
    assert not manager._rule_is_due(rule, date(2027, 2, 27))


async def test_recurrence_rule_can_be_updated_and_deactivated(manager):
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Müll", 3)
    rule = await manager.async_create_recurrence_rule(
        chore_type.id, date(2027, 7, 1), frequency="days"
    )

    updated = await manager.async_update_recurrence_rule(
        rule["id"], interval=2, active=False
    )

    assert updated["interval"] == 2
    assert updated["active"] is False
    assert await manager.async_materialize_recurrences(date(2027, 7, 3)) == 0


async def test_deleting_recurrence_rule_preserves_generated_tasks(manager):
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Müll", 3)
    start = manager.today()
    rule = await manager.async_create_recurrence_rule(
        chore_type.id, start, frequency="days"
    )
    task_ids = set(manager.data.tasks)

    await manager.async_delete_recurrence_rule(rule["id"])

    assert rule["id"] not in manager.data.recurrence_rules
    assert set(manager.data.tasks) == task_ids


async def test_child_cannot_complete_adult_only_task_without_permission(manager):
    await manager.async_load()
    child = await manager.async_create_participant("Kind")
    restricted = await manager.async_create_chore_type(
        "Backofen reinigen", 5, adult_only=True
    )
    task = await manager.async_create_task(restricted.id, manager.today())
    with pytest.raises(ValidationError):
        await manager.async_complete_task(task.id, child.id)

    await manager.async_update_participant(
        child.id, can_do_restricted_tasks=True
    )
    await manager.async_complete_task(task.id, child.id)


async def test_week_points_keep_normal_and_race_scores_separate(manager):
    participant, _, task = await _base_records(manager)
    await manager.async_complete_task(task.id, participant.id)
    second = await manager.async_create_task(task.chore_type_id, manager.today())
    race = await manager.async_complete_task(second.id, participant.id)
    race.scoring_mode = ScoringMode.RACE
    race.race_id = "race-1"

    assert manager.points_week_all()[participant.id] == 2
    assert manager.normal_points_week()[participant.id] == 1
    assert manager.race_points_week()[participant.id] == 1
    assert manager.race_points_week("race-1")[participant.id] == 1
    assert manager.week_leader() == participant
