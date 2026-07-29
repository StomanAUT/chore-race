"""Business-rule tests for Chore Race Core."""

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from custom_components.chore_race import manager as manager_module
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


async def test_open_task_can_be_edited_and_deleted(manager):
    participant, _, task = await _base_records(manager)
    replacement = await manager.async_create_chore_type("Bad reinigen", 8)
    new_date = manager.today() + timedelta(days=1)

    updated = await manager.async_update_task(
        task.id,
        chore_type_id=replacement.id,
        date=new_date,
        race_points=7,
        preferred_participant_id=participant.id,
        blocked=True,
    )

    assert updated.chore_type_id == replacement.id
    assert updated.date == new_date
    assert updated.race_points == 7
    assert updated.blocked is True

    await manager.async_delete_task(task.id)
    assert task.id not in manager.data.tasks


async def test_task_can_target_home_assistant_floor(manager, monkeypatch):
    """A task may cover one HA floor instead of one individual area."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Boden wischen", 5)
    registry = SimpleNamespace(
        async_get_floor=lambda floor_id: (
            SimpleNamespace(floor_id=floor_id, name="Erdgeschoss")
            if floor_id == "erdgeschoss"
            else None
        )
    )
    monkeypatch.setattr(
        manager_module.fr, "async_get", lambda hass: registry
    )

    task = await manager.async_create_task(
        chore_type.id,
        manager.today(),
        floor_id="erdgeschoss",
    )

    assert task.floor_id == "erdgeschoss"
    assert task.area_id is None
    assert task.to_dict()["floor_id"] == "erdgeschoss"


async def test_task_rejects_area_and_floor_combination(manager):
    """Room and floor scopes are alternatives, never cumulative filters."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Boden wischen", 5)

    with pytest.raises(ValidationError, match="either an area or a floor"):
        await manager.async_create_task(
            chore_type.id,
            manager.today(),
            area_id="wohnzimmer",
            floor_id="erdgeschoss",
        )


async def test_task_can_switch_from_area_to_floor(manager, monkeypatch):
    """An untouched task can replace its room assignment with a floor."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Boden wischen", 5)
    area_registry = SimpleNamespace(
        async_get_area=lambda area_id: (
            SimpleNamespace(id=area_id, name="Wohnzimmer")
            if area_id == "wohnzimmer"
            else None
        )
    )
    floor_registry = SimpleNamespace(
        async_get_floor=lambda floor_id: (
            SimpleNamespace(floor_id=floor_id, name="Erdgeschoss")
            if floor_id == "erdgeschoss"
            else None
        )
    )
    monkeypatch.setattr(
        manager_module.ar, "async_get", lambda hass: area_registry
    )
    monkeypatch.setattr(
        manager_module.fr, "async_get", lambda hass: floor_registry
    )
    task = await manager.async_create_task(
        chore_type.id,
        manager.today(),
        area_id="wohnzimmer",
    )

    updated = await manager.async_update_task(
        task.id,
        area_id=None,
        floor_id="erdgeschoss",
    )

    assert updated.area_id is None
    assert updated.floor_id == "erdgeschoss"


async def test_unknown_home_assistant_floor_is_rejected(manager, monkeypatch):
    """Stored floor IDs must resolve through Home Assistant's registry."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Boden wischen", 5)
    registry = SimpleNamespace(async_get_floor=lambda floor_id: None)
    monkeypatch.setattr(
        manager_module.fr, "async_get", lambda hass: registry
    )

    with pytest.raises(ValidationError, match="floor"):
        await manager.async_create_task(
            chore_type.id,
            manager.today(),
            floor_id="gibt-es-nicht",
        )


async def test_task_with_completion_history_cannot_be_changed(manager):
    participant, _, task = await _base_records(manager)
    completion = await manager.async_complete_task(task.id, participant.id)
    await manager.async_undo_completion(completion.id)

    with pytest.raises(ConflictError):
        await manager.async_update_task(task.id, race_points=9)
    with pytest.raises(ConflictError):
        await manager.async_delete_task(task.id)


async def test_untouched_open_tasks_can_change_during_running_race(manager):
    _, chore_type, task = await _base_records(manager)
    await manager.async_start_race()

    updated = await manager.async_update_task(task.id, race_points=9)
    assert updated.race_points == 9
    assert manager.race_state()["current_task"]["race_points"] == 9

    second = await manager.async_create_task(chore_type.id, manager.today())
    await manager.async_delete_task(second.id)
    assert second.id not in manager.data.tasks
    assert all(
        item["id"] != second.id
        for item in manager.race_state()["open_tasks"]
    )


async def test_only_unused_chore_types_can_be_deleted(manager):
    await manager.async_load()
    unused = await manager.async_create_chore_type("Fenster", 5)
    await manager.async_delete_chore_type(unused.id)
    assert unused.id not in manager.data.chore_types

    used = await manager.async_create_chore_type("Boden", 4)
    await manager.async_create_task(used.id, manager.today())
    with pytest.raises(ConflictError):
        await manager.async_delete_chore_type(used.id)


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


async def test_recurring_floor_assignment_is_materialized(manager, monkeypatch):
    """Generated tasks retain the floor scope of their recurrence rule."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Boden wischen", 5)
    registry = SimpleNamespace(
        async_get_floor=lambda floor_id: (
            SimpleNamespace(floor_id=floor_id, name="Obergeschoss")
            if floor_id == "obergeschoss"
            else None
        )
    )
    monkeypatch.setattr(
        manager_module.fr, "async_get", lambda hass: registry
    )
    start = manager.today() + timedelta(days=1)

    rule = await manager.async_create_recurrence_rule(
        chore_type.id,
        start,
        frequency="days",
        floor_id="obergeschoss",
    )
    assert rule["floor_id"] == "obergeschoss"
    assert rule["area_id"] is None

    assert await manager.async_materialize_recurrences(start) == 1
    generated = [
        task
        for task in manager.data.tasks.values()
        if task.source_entity_id == f"recurrence:{rule['id']}"
    ]
    assert len(generated) == 1
    assert generated[0].floor_id == "obergeschoss"
    assert generated[0].area_id is None


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


async def test_race_transitions_and_countdown(manager):
    await manager.async_load()

    ready = manager.race_state()
    assert ready["status"] == "ready"
    assert ready["remaining_seconds"] == 0

    running = await manager.async_start_race()
    assert running["status"] == "running"
    assert running["race_id"]
    assert 1798 <= running["remaining_seconds"] <= 1800

    with pytest.raises(ConflictError):
        await manager.async_start_race()

    finished = await manager.async_stop_race()
    assert finished["status"] == "finished"
    assert finished["race_id"] == running["race_id"]
    assert finished["remaining_seconds"] == 0


async def test_completion_during_race_persists_race_score(manager):
    participant, _, task = await _base_records(manager)
    race = await manager.async_start_race()

    completion = await manager.async_complete_task(task.id, participant.id)

    assert completion.scoring_mode is ScoringMode.RACE
    assert completion.race_id == race["race_id"]
    assert completion.total_points_awarded == task.race_points
    assert manager.race_points_week(race["race_id"])[participant.id] == 5
    assert manager.normal_points_week()[participant.id] == 0
    assert manager.week_leader() == participant
    assert manager.race_state()["leaderboard"][0]["points"] == 5


async def test_race_state_exposes_open_task_and_updates_immediately(manager):
    participant, chore_type, task = await _base_records(manager)
    await manager.async_start_race()

    before = manager.race_state()
    assert before["current_task"]["id"] == task.id
    assert before["current_task"]["name"] == chore_type.name
    assert "image" in before["current_task"]
    assert "icon" in before["current_task"]
    assert len(before["open_tasks"]) == 1

    await manager.async_complete_task(
        task.id, participant.id, require_active_race=True
    )

    after = manager.race_state()
    assert after["current_task"] is None
    assert after["open_tasks"] == []
    assert after["leaderboard"][0]["points"] == task.race_points


async def test_race_completion_requires_running_session(manager):
    participant, _, task = await _base_records(manager)

    with pytest.raises(ConflictError, match="No race is running"):
        await manager.async_complete_task(
            task.id, participant.id, require_active_race=True
        )


async def test_race_scoring_awards_fair_play_streak_and_copilot(manager):
    driver, chore_type, first_task = await _base_records(manager)
    copilot = await manager.async_create_participant("Viktoria")
    await manager.async_update_chore_type(
        chore_type.id,
        streak_enabled=True,
        streak_max_bonus=2,
        default_copilot_points=2,
    )
    race = await manager.async_start_race()

    first = await manager.async_complete_task(
        first_task.id,
        driver.id,
        require_active_race=True,
        fair_play=True,
    )
    second_task = await manager.async_create_task(
        chore_type.id, manager.today()
    )
    second = await manager.async_complete_task(
        second_task.id,
        driver.id,
        require_active_race=True,
        copilot_participant_id=copilot.id,
    )

    assert first.base_points_awarded == 5
    assert first.fair_play_bonus == 1
    assert first.streak_bonus == 0
    assert first.total_points_awarded == 6
    assert second.streak_bonus == 1
    assert second.copilot_points_awarded == 2
    assert second.total_points_awarded == 6

    state = manager.race_state(race["race_id"])
    assert state["leaderboard"][0] == {
        "participant_id": driver.id,
        "name": driver.name,
        "points": 12,
        "base_points": 10,
        "fair_play_bonus": 1,
        "streak_bonus": 1,
        "copilot_points": 0,
        "rank": 1,
    }
    assert state["leaderboard"][1]["points"] == 2
    assert state["leaderboard"][1]["copilot_points"] == 2
    assert state["last_completion"]["participant_name"] == driver.name
    assert state["last_completion"]["copilot_name"] == copilot.name


async def test_race_bonus_validation_and_streak_cap(manager):
    driver, chore_type, first_task = await _base_records(manager)
    copilot = await manager.async_create_participant("Julia")
    await manager.async_update_chore_type(
        chore_type.id, streak_enabled=True, streak_max_bonus=1
    )
    await manager.async_start_race()

    with pytest.raises(
        ValidationError, match="cannot be combined"
    ):
        await manager.async_complete_task(
            first_task.id,
            driver.id,
            require_active_race=True,
            copilot_participant_id=copilot.id,
            fair_play=True,
        )
    with pytest.raises(ValidationError, match="must be different"):
        await manager.async_complete_task(
            first_task.id,
            driver.id,
            require_active_race=True,
            copilot_participant_id=driver.id,
        )

    await manager.async_complete_task(
        first_task.id, driver.id, require_active_race=True
    )
    second_task = await manager.async_create_task(
        chore_type.id, manager.today()
    )
    third_task = await manager.async_create_task(
        chore_type.id, manager.today()
    )
    second = await manager.async_complete_task(
        second_task.id, driver.id, require_active_race=True
    )
    third = await manager.async_complete_task(
        third_task.id, driver.id, require_active_race=True
    )
    assert second.streak_bonus == 1
    assert third.streak_bonus == 1


async def test_finished_race_exposes_unique_champion_and_ties(manager):
    driver, _, task = await _base_records(manager)
    race = await manager.async_start_race()
    await manager.async_complete_task(
        task.id, driver.id, require_active_race=True
    )

    finished = await manager.async_stop_race()

    assert finished["race_id"] == race["race_id"]
    assert finished["champion"]["participant_id"] == driver.id
    assert finished["champion"]["points"] == task.race_points
