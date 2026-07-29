"""Serialization and historical snapshot tests."""

from datetime import UTC, date, datetime

from custom_components.chore_race.models import (
    ChoreRaceData,
    ChoreTask,
    ChoreType,
    Reward,
    RewardSelection,
)


def test_round_trip_storage_data():
    """Persisted state restores typed dates, datetimes and enums."""
    now = datetime(2026, 7, 28, 12, tzinfo=UTC)
    chore_type = ChoreType(id="type", name="Aufräumen", default_race_points=5)
    task = ChoreTask(
        id="task",
        chore_type_id=chore_type.id,
        date=date(2026, 7, 28),
        race_points=5,
        created_at=now,
        updated_at=now,
    )
    reward = Reward(id="reward", name="Filmabend")
    selection = RewardSelection(
        id="selection",
        race_id="race",
        reward_id=reward.id,
        participant_id="participant",
        selected_at=now,
    )
    original = ChoreRaceData(
        chore_types={chore_type.id: chore_type},
        tasks={task.id: task},
        rewards={reward.id: reward},
        reward_selections={selection.id: selection},
    )

    restored = ChoreRaceData.from_dict(original.to_dict())

    assert restored.to_dict() == original.to_dict()
    assert restored.tasks["task"].race_points == 5
    assert restored.reward_selections["selection"].selected_at == now
