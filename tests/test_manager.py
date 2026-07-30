"""Business-rule tests for Chore Race Core."""

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from custom_components.chore_race import manager as manager_module
from custom_components.chore_race.const import EVENT_TASK_CREATED
from custom_components.chore_race.errors import ConflictError, ValidationError
from custom_components.chore_race.models import ScoringMode, TaskSource, TaskStatus


async def _base_records(manager):
    await manager.async_load()
    participant = await manager.async_create_participant("Arthur")
    chore_type = await manager.async_create_chore_type("Aufräumen", 5)
    task = await manager.async_create_task(
        chore_type.id,
        manager.today(),
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


async def test_ensure_task_is_idempotent_for_derived_daily_key(manager):
    """Repeated automation calls create one concrete task for the same day."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Waschmaschine", 3)

    first = await manager.async_ensure_task(
        chore_type.id,
        manager.today(),
        source=TaskSource.ENTITY,
        source_entity_id="sensor.washing_machine_state",
    )
    repeated = await manager.async_ensure_task(
        chore_type.id,
        manager.today(),
        source=TaskSource.ENTITY,
        source_entity_id="sensor.washing_machine_state",
    )

    assert first["created"] is True
    assert repeated["created"] is False
    assert repeated["task"]["id"] == first["task"]["id"]
    assert len(manager.data.tasks) == 1
    assert manager.automatic_tasks_today() == 1


async def test_ensure_task_is_atomic_for_concurrent_automation_calls(manager):
    """Concurrent retries with one explicit event key cannot create duplicates."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Müll rausbringen", 2)

    results = await asyncio.gather(
        *(
            manager.async_ensure_task(
                chore_type.id,
                manager.today(),
                source=TaskSource.AUTOMATION,
                source_entity_id="automation.bin_reminder",
                deduplication_key="bin-reminder-2026-w31",
            )
            for _ in range(5)
        )
    )

    assert sum(result["created"] for result in results) == 1
    assert len({result["task"]["id"] for result in results}) == 1
    assert len(manager.data.tasks) == 1


async def test_ensure_task_fires_one_attributed_created_event(manager, hass):
    """Only the first idempotent call announces a newly persisted task."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Geschirrspüler", 2)
    events = []
    remove_listener = hass.bus.async_listen(
        EVENT_TASK_CREATED, lambda event: events.append(event.data)
    )

    try:
        first = await manager.async_ensure_task(
            chore_type.id,
            manager.today(),
            source=TaskSource.ENTITY,
            source_entity_id="sensor.dishwasher_state",
        )
        await manager.async_ensure_task(
            chore_type.id,
            manager.today(),
            source=TaskSource.ENTITY,
            source_entity_id="sensor.dishwasher_state",
        )
        await hass.async_block_till_done()
    finally:
        remove_listener()

    assert events == [
        {
            "task_id": first["task"]["id"],
            "source": "entity",
            "source_entity_id": "sensor.dishwasher_state",
        }
    ]


async def test_ensure_task_key_can_distinguish_automation_events(manager):
    """Explicit event keys allow several tasks from the same source and date."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Trockner ausräumen", 2)

    first = await manager.async_ensure_task(
        chore_type.id,
        manager.today(),
        source="automation",
        source_entity_id="automation.dryer_finished",
        deduplication_key="dryer-cycle-41",
    )
    second = await manager.async_ensure_task(
        chore_type.id,
        manager.today(),
        source="automation",
        source_entity_id="automation.dryer_finished",
        deduplication_key="dryer-cycle-42",
    )

    assert first["created"] is True
    assert second["created"] is True
    assert first["task"]["id"] != second["task"]["id"]


async def test_ensure_task_rejects_non_automatic_sources(manager):
    """The idempotent helper is reserved for entity and automation sources."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Fenster öffnen", 1)

    with pytest.raises(ValidationError, match="entity or automation"):
        await manager.async_ensure_task(
            chore_type.id,
            manager.today(),
            source=TaskSource.MANUAL,
            source_entity_id="input_button.create_chore",
        )


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
    """A floor task snapshots base points times its assigned room count."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Boden wischen", 5)
    floor_registry = SimpleNamespace(
        async_get_floor=lambda floor_id: (
            SimpleNamespace(floor_id=floor_id, name="Erdgeschoss")
            if floor_id == "erdgeschoss"
            else None
        )
    )
    area_registry = SimpleNamespace(
        async_list_areas=lambda: [
            SimpleNamespace(id="wohnzimmer", floor_id="erdgeschoss"),
            SimpleNamespace(id="esszimmer", floor_id="erdgeschoss"),
            SimpleNamespace(id="kueche", floor_id="erdgeschoss"),
            SimpleNamespace(id="bad", floor_id="obergeschoss"),
        ]
    )
    monkeypatch.setattr(
        manager_module.fr, "async_get", lambda hass: floor_registry
    )
    monkeypatch.setattr(
        manager_module.ar, "async_get", lambda hass: area_registry
    )

    task = await manager.async_create_task(
        chore_type.id,
        manager.today(),
        floor_id="erdgeschoss",
    )

    assert task.floor_id == "erdgeschoss"
    assert task.area_id is None
    assert task.base_race_points == 5
    assert task.points_multiplier == 3
    assert task.race_points == 15
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
        ),
        async_list_areas=lambda: [
            SimpleNamespace(id="wohnzimmer", floor_id="erdgeschoss"),
            SimpleNamespace(id="esszimmer", floor_id="erdgeschoss"),
        ],
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
    assert updated.base_race_points == 5
    assert updated.points_multiplier == 2
    assert updated.race_points == 10


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


async def test_floor_without_assigned_rooms_is_rejected(manager, monkeypatch):
    """A floor multiplier cannot silently create a zero-room assignment."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Boden wischen", 1)
    monkeypatch.setattr(
        manager_module.fr,
        "async_get",
        lambda hass: SimpleNamespace(
            async_get_floor=lambda floor_id: SimpleNamespace(
                floor_id=floor_id, name="Leer"
            )
        ),
    )
    monkeypatch.setattr(
        manager_module.ar,
        "async_get",
        lambda hass: SimpleNamespace(async_list_areas=lambda: []),
    )

    with pytest.raises(ValidationError, match="no assigned areas"):
        await manager.async_create_task(
            chore_type.id,
            manager.today(),
            floor_id="leer",
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
    monkeypatch.setattr(
        manager_module.ar,
        "async_get",
        lambda hass: SimpleNamespace(
            async_list_areas=lambda: [
                SimpleNamespace(id="schlafzimmer", floor_id="obergeschoss"),
                SimpleNamespace(id="bad", floor_id="obergeschoss"),
            ]
        ),
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
    assert generated[0].base_race_points == 5
    assert generated[0].points_multiplier == 2
    assert generated[0].race_points == 10


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


async def test_weekday_rule_materializes_only_selected_days(manager):
    """Weekday schedules use Monday=0 through Sunday=6."""
    await manager.async_load()
    chore_type = await manager.async_create_chore_type("Staubsaugen", 4)
    monday = date(2027, 8, 2)
    rule = await manager.async_create_recurrence_rule(
        chore_type.id,
        monday,
        frequency="weekdays",
        weekdays=[0, 2],
    )

    assert manager._rule_is_due(rule, monday)
    assert not manager._rule_is_due(rule, date(2027, 8, 3))
    assert manager._rule_is_due(rule, date(2027, 8, 4))
    assert await manager.async_materialize_recurrences(monday) == 1
    assert await manager.async_materialize_recurrences(date(2027, 8, 4)) == 1

    with pytest.raises(ValidationError, match="At least one weekday"):
        await manager.async_create_recurrence_rule(
            chore_type.id,
            monday,
            frequency="weekdays",
            weekdays=[],
        )


async def test_completion_interval_waits_since_last_completion(manager):
    """A completion-based rule never duplicates open work."""
    await manager.async_load()
    participant = await manager.async_create_participant("Arthur")
    chore_type = await manager.async_create_chore_type("WC reinigen", 8)
    start = manager.today()
    rule = await manager.async_create_recurrence_rule(
        chore_type.id,
        start,
        frequency="completion_interval",
        interval=7,
    )
    generated = [
        task
        for task in manager.data.tasks.values()
        if task.source_entity_id == f"recurrence:{rule['id']}"
    ]
    assert len(generated) == 1
    assert await manager.async_materialize_recurrences(start + timedelta(days=8)) == 0

    await manager.async_complete_task(generated[0].id, participant.id)

    assert await manager.async_materialize_recurrences(start + timedelta(days=6)) == 0
    assert await manager.async_materialize_recurrences(start + timedelta(days=7)) == 1
    assert await manager.async_materialize_recurrences(start + timedelta(days=8)) == 0


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


async def test_champion_selects_one_auditable_reward(manager):
    driver, _, task = await _base_records(manager)
    reward = await manager.async_create_reward(
        "Filmabend", icon="mdi:movie-open"
    )
    race = await manager.async_start_race()
    await manager.async_complete_task(
        task.id, driver.id, require_active_race=True
    )
    await manager.async_stop_race()

    selection = await manager.async_select_reward(race["race_id"], reward.id)
    state = manager.race_state(race["race_id"])

    assert selection["participant_id"] == driver.id
    assert selection["participant_name"] == driver.name
    assert selection["reward_name"] == reward.name
    assert state["reward_selection"]["id"] == selection["id"]
    assert state["last_reward_selection"]["id"] == selection["id"]

    with pytest.raises(ConflictError, match="already selected"):
        await manager.async_select_reward(race["race_id"], reward.id)
    with pytest.raises(ConflictError, match="must be deactivated"):
        await manager.async_delete_reward(reward.id)


async def test_reward_selection_requires_finished_race_champion(manager):
    _, _, _ = await _base_records(manager)
    reward = await manager.async_create_reward("Eis essen")
    race = await manager.async_start_race()

    with pytest.raises(ConflictError, match="after a race"):
        await manager.async_select_reward(race["race_id"], reward.id)

    await manager.async_stop_race()
    with pytest.raises(ConflictError, match="unique champion"):
        await manager.async_select_reward(race["race_id"], reward.id)


async def test_reset_selected_race_reverts_only_its_completions(manager):
    """A reset reopens its race tasks without touching unrelated points."""
    participant, chore_type, normal_task = await _base_records(manager)
    normal_completion = await manager.async_complete_task(
        normal_task.id, participant.id
    )
    first_race_task = await manager.async_create_task(
        chore_type.id, manager.today()
    )
    first_race = await manager.async_start_race()
    first_race_completion = await manager.async_complete_task(
        first_race_task.id,
        participant.id,
        require_active_race=True,
    )
    await manager.async_stop_race()

    second_race_task = await manager.async_create_task(
        chore_type.id, manager.today()
    )
    second_race = await manager.async_start_race()
    second_race_completion = await manager.async_complete_task(
        second_race_task.id,
        participant.id,
        require_active_race=True,
    )

    reset = await manager.async_reset_race(first_race["race_id"])

    assert reset["race_id"] == first_race["race_id"]
    assert reset["status"] == "ready"
    assert reset["reset_at"] is not None
    assert reset["participant_ids"] == [participant.id]
    assert first_race_completion.active is False
    assert first_race_task.status is TaskStatus.OPEN
    assert normal_completion.active is True
    assert normal_task.status is TaskStatus.COMPLETED
    assert second_race_completion.active is True
    assert second_race_task.status is TaskStatus.COMPLETED
    assert manager.normal_points_week()[participant.id] == 1
    assert manager.race_points_week(first_race["race_id"])[participant.id] == 0
    assert (
        manager.race_points_week(second_race["race_id"])[participant.id]
        == second_race_task.race_points
    )
    assert manager.race_state(second_race["race_id"])["status"] == "running"


async def test_reset_current_race_restores_current_active_roster(manager):
    """Reset without an ID targets the current race and refreshes its roster."""
    participant, _, task = await _base_records(manager)
    removed_before_reset = await manager.async_create_participant("Viktoria")
    race = await manager.async_start_race()
    completion = await manager.async_complete_task(
        task.id, participant.id, require_active_race=True
    )
    await manager.async_update_participant(
        removed_before_reset.id, active=False
    )
    added_after_start = await manager.async_create_participant("Manuel")

    reset = await manager.async_reset_race()

    assert reset["race_id"] == race["race_id"]
    assert reset["status"] == "ready"
    assert set(reset["participant_ids"]) == {
        participant.id,
        added_after_start.id,
    }
    assert completion.active is False
    assert task.status is TaskStatus.OPEN


async def test_remove_race_participant_is_local_and_reverts_their_roles(manager):
    """Removing a racer preserves the person and unrelated race completions."""
    driver, chore_type, driver_task = await _base_records(manager)
    removed = await manager.async_create_participant("Viktoria")
    unaffected = await manager.async_create_participant("Manuel")
    copilot_task = await manager.async_create_task(
        chore_type.id, manager.today()
    )
    unaffected_task = await manager.async_create_task(
        chore_type.id, manager.today()
    )
    race = await manager.async_start_race()
    removed_as_driver = await manager.async_complete_task(
        driver_task.id,
        removed.id,
        require_active_race=True,
    )
    removed_as_copilot = await manager.async_complete_task(
        copilot_task.id,
        driver.id,
        require_active_race=True,
        copilot_participant_id=removed.id,
    )
    unrelated_completion = await manager.async_complete_task(
        unaffected_task.id,
        unaffected.id,
        require_active_race=True,
    )

    state = await manager.async_remove_race_participant(
        removed.id, race["race_id"]
    )

    assert removed.id not in state["participant_ids"]
    assert removed.id not in {
        row["participant_id"] for row in state["leaderboard"]
    }
    assert manager.data.participants[removed.id].active is True
    assert removed_as_driver.active is False
    assert removed_as_copilot.active is False
    assert driver_task.status is TaskStatus.OPEN
    assert copilot_task.status is TaskStatus.OPEN
    assert unrelated_completion.active is True
    assert unaffected_task.status is TaskStatus.COMPLETED
    assert state["leaderboard"][0]["participant_id"] == unaffected.id
    assert state["leaderboard"][0]["points"] == unaffected_task.race_points


async def test_ready_race_adds_new_participants_but_keeps_removals_excluded(manager):
    """A new planner participant joins the lineup without restoring removals."""
    original, _, _ = await _base_records(manager)
    race = await manager.async_start_race()
    await manager.async_reset_race(race["race_id"])
    removed = await manager.async_remove_race_participant(
        original.id, race["race_id"]
    )

    assert removed["participant_ids"] == []
    newcomer = await manager.async_create_participant("Julia")
    state = manager.race_state(race["race_id"])

    assert state["participant_ids"] == [newcomer.id]
    assert [row["participant_id"] for row in state["leaderboard"]] == [
        newcomer.id
    ]
    assert original.id not in state["participant_ids"]


async def test_legacy_ready_race_recovers_active_participants(manager):
    """Ready sessions created before exclusion tracking gain active people."""
    participant, _, _ = await _base_records(manager)
    race = await manager.async_start_race()
    await manager.async_reset_race(race["race_id"])
    stored = manager.data.race_sessions[race["race_id"]]
    stored["participant_ids"] = []
    stored.pop("excluded_participant_ids")

    state = manager.race_state(race["race_id"])

    assert state["participant_ids"] == [participant.id]
    assert state["leaderboard"][0]["participant_id"] == participant.id
