"""Serialization and historical snapshot tests."""

from datetime import UTC, date, datetime

import pytest

from custom_components.chore_race.models import (
    ChoreRaceData,
    ChoreTask,
    ChoreType,
    Reward,
    RewardSelection,
    TaskChain,
    TaskChainStep,
    TaskSource,
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
        source=TaskSource.AUTOMATION,
        source_entity_id="automation.create_daily_chore",
        deduplication_key="daily-chore-2026-07-28",
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
    assert restored.tasks["task"].deduplication_key == "daily-chore-2026-07-28"
    assert restored.reward_selections["selection"].selected_at == now


def test_task_chain_round_trip_preserves_typed_steps():
    """Canonical chain data restores as typed records with stable IDs."""
    chain = TaskChain(
        id="laundry",
        name="Wäsche",
        steps={
            "unload": TaskChainStep(
                id="unload",
                chain_id="laundry",
                chore_type_id="washing-machine-unload",
                order=0,
            ),
            "hang": TaskChainStep(
                id="hang",
                chain_id="laundry",
                chore_type_id="hang-laundry",
                order=1,
                unlock_after_step_ids=["unload"],
            ),
            "put-away": TaskChainStep(
                id="put-away",
                chain_id="laundry",
                chore_type_id="put-away-laundry",
                order=2,
                unlock_after_step_ids=["hang"],
            ),
        },
    )
    original = ChoreRaceData(task_chains={chain.id: chain})

    restored = ChoreRaceData.from_dict(original.to_dict())

    assert restored.to_dict() == original.to_dict()
    assert isinstance(restored.task_chains["laundry"], TaskChain)
    assert isinstance(
        restored.task_chains["laundry"].steps["hang"], TaskChainStep
    )


def test_task_chain_loads_legacy_dictionary_shape():
    """Reserved v1 dictionaries are upgraded without a schema bump."""
    restored = ChoreRaceData.from_dict(
        {
            "task_chains": {
                "laundry": {
                    "name": "Wäsche",
                    "steps": [
                        {
                            "id": "unload",
                            "chore_type_id": "washing-machine-unload",
                            "order": 0,
                        },
                        {
                            "id": "hang",
                            "chore_type_id": "hang-laundry",
                            "order": 1,
                            "unlock_after_step_id": "unload",
                        },
                    ],
                }
            }
        }
    )

    chain = restored.task_chains["laundry"]
    assert chain.id == "laundry"
    assert chain.steps["unload"].chain_id == "laundry"
    assert chain.steps["hang"].unlock_after_step_ids == ["unload"]
    assert chain.to_dict()["steps"]["hang"]["unlock_after_step_ids"] == [
        "unload"
    ]


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        (
            {
                "hang": TaskChainStep(
                    id="hang",
                    chain_id="laundry",
                    chore_type_id="hang-laundry",
                    order=1,
                    unlock_after_step_ids=["missing"],
                )
            },
            "unknown dependency",
        ),
        (
            {
                "unload": TaskChainStep(
                    id="unload",
                    chain_id="laundry",
                    chore_type_id="unload",
                    order=0,
                ),
                "hang": TaskChainStep(
                    id="hang",
                    chain_id="laundry",
                    chore_type_id="hang",
                    order=0,
                ),
            },
            "order must be unique",
        ),
        (
            {
                "later": TaskChainStep(
                    id="later",
                    chain_id="laundry",
                    chore_type_id="later",
                    order=1,
                ),
                "first": TaskChainStep(
                    id="first",
                    chain_id="laundry",
                    chore_type_id="first",
                    order=0,
                    unlock_after_step_ids=["later"],
                ),
            },
            "must precede",
        ),
    ],
)
def test_task_chain_rejects_invalid_dependencies(steps, message):
    """Unknown, ambiguous and forward dependencies are rejected."""
    with pytest.raises(ValueError, match=message):
        TaskChain(id="laundry", name="Wäsche", steps=steps)


def test_task_chain_step_rejects_unstable_id():
    """Whitespace-normalized IDs cannot silently change after persistence."""
    with pytest.raises(ValueError, match="surrounding whitespace"):
        TaskChainStep(
            id=" hang",
            chain_id="laundry",
            chore_type_id="hang-laundry",
            order=0,
        )


def test_legacy_keyed_record_without_embedded_id_is_restored():
    """The stable dictionary key fills an ID omitted by early snapshots."""
    restored = ChoreRaceData.from_dict(
        {"participants": {"julia": {"name": "Julia"}}}
    )

    assert restored.participants["julia"].id == "julia"
    assert restored.to_dict()["participants"]["julia"]["id"] == "julia"


def test_conflicting_embedded_record_id_is_rejected():
    """A dictionary key cannot silently disagree with persisted identity."""
    with pytest.raises(ValueError, match="conflicting embedded ID"):
        ChoreRaceData.from_dict(
            {
                "participants": {
                    "julia": {"id": "someone-else", "name": "Julia"}
                }
            }
        )


@pytest.mark.parametrize(
    ("snapshot", "message"),
    [
        ({"participants": []}, "participants must be a dictionary"),
        (
            {"participants": {"julia": "not-a-record"}},
            "participants record 'julia' must be a dictionary",
        ),
        (
            {"race_sessions": {"race": []}},
            "race_sessions record 'race' must be a dictionary",
        ),
        ({"settings": []}, "settings must be a dictionary"),
    ],
)
def test_malformed_storage_containers_are_rejected(snapshot, message):
    """Damaged collections fail with an actionable storage path."""
    with pytest.raises(ValueError, match=message):
        ChoreRaceData.from_dict(snapshot)


def test_duplicate_legacy_task_chain_step_ids_are_rejected():
    """List-based legacy chains cannot silently overwrite a prior step."""
    with pytest.raises(ValueError, match="must be unique"):
        ChoreRaceData.from_dict(
            {
                "task_chains": {
                    "laundry": {
                        "name": "Laundry",
                        "steps": [
                            {"id": "wash", "chore_type_id": "wash"},
                            {"id": "wash", "chore_type_id": "dry"},
                        ],
                    }
                }
            }
        )


def test_malformed_legacy_task_chain_step_is_rejected_cleanly():
    """A damaged list step reports its storage shape instead of crashing."""
    with pytest.raises(ValueError, match="step must be a dictionary"):
        ChoreRaceData.from_dict(
            {
                "task_chains": {
                    "laundry": {
                        "name": "Laundry",
                        "steps": ["not-a-step"],
                    }
                }
            }
        )
