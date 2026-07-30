"""Storage adapter restart test."""

import copy
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.chore_race.models import (
    ChoreRaceData,
    Participant,
    TaskChain,
)
from custom_components.chore_race.storage import ChoreRaceStore


async def test_save_load_simulated_restart(hass):
    """A serialized snapshot restores after constructing a new adapter."""
    raw = ChoreRaceData(
        participants={"stable": Participant(id="stable", name="Julia")}
    ).to_dict()
    backend = AsyncMock()
    backend.async_load.return_value = raw

    with patch(
        "custom_components.chore_race.storage.Store", return_value=backend
    ):
        restarted_store = ChoreRaceStore(hass)
        restored = await restarted_store.async_load()

    assert restored.participants["stable"].name == "Julia"
    assert restored.participants["stable"].id == "stable"


async def test_load_migrates_legacy_task_chain_dictionaries(hass):
    """Existing untyped v1 chain records load as typed domain records."""
    backend = AsyncMock()
    backend.async_load.return_value = {
        "schema_version": 1,
        "task_chains": {
            "laundry": {
                "name": "Wäsche",
                "steps": {
                    "unload": {
                        "chore_type_id": "washing-machine-unload",
                        "order": 0,
                    },
                    "hang": {
                        "chore_type_id": "hang-laundry",
                        "order": 1,
                        "unlock_after_step_id": "unload",
                    },
                },
            }
        },
    }

    with patch(
        "custom_components.chore_race.storage.Store", return_value=backend
    ):
        restored = await ChoreRaceStore(hass).async_load()

    chain = restored.task_chains["laundry"]
    assert isinstance(chain, TaskChain)
    assert chain.steps["hang"].unlock_after_step_ids == ["unload"]


async def test_save_writes_canonical_task_chain_shape(hass):
    """A legacy snapshot is canonicalized on its next regular save."""
    backend = AsyncMock()
    backend.async_load.return_value = {
        "task_chains": {
            "laundry": {
                "name": "Wäsche",
                "steps": [
                    {
                        "id": "unload",
                        "chore_type_id": "washing-machine-unload",
                    }
                ],
            }
        }
    }

    with patch(
        "custom_components.chore_race.storage.Store", return_value=backend
    ):
        store = ChoreRaceStore(hass)
        restored = await store.async_load()
        await store.async_save(restored)

    saved = backend.async_save.await_args.args[0]
    step = saved["task_chains"]["laundry"]["steps"]["unload"]
    assert step == {
        "id": "unload",
        "chain_id": "laundry",
        "chore_type_id": "washing-machine-unload",
        "order": 0,
        "unlock_after_step_ids": [],
    }


def test_migrate_normalizes_missing_v1_collections_without_mutating_input():
    """Early v1 snapshots gain additive collections on a detached root."""
    raw = {"participants": {"julia": {"id": "julia", "name": "Julia"}}}
    original = copy.deepcopy(raw)

    migrated = ChoreRaceStore._migrate(raw)

    assert raw == original
    assert migrated is not raw
    assert migrated["schema_version"] == 1
    assert migrated["task_chains"] == {}
    assert migrated["reward_selections"] == {}
    assert migrated["settings"] == {}


@pytest.mark.parametrize("version", [0, 2, True, "1", 1.0])
def test_migrate_rejects_unsupported_or_invalid_schema_versions(version):
    """Only the explicitly supported logical schema is accepted."""
    with pytest.raises(ValueError, match="schema version"):
        ChoreRaceStore._migrate({"schema_version": version})


def test_migrate_rejects_non_dictionary_root():
    """A corrupt root fails before model restoration."""
    with pytest.raises(ValueError, match="root must be a dictionary"):
        ChoreRaceStore._migrate([])  # type: ignore[arg-type]


async def test_save_rejects_unsupported_logical_schema(hass):
    """Unsupported snapshots are never persisted over recoverable data."""
    backend = AsyncMock()
    with patch(
        "custom_components.chore_race.storage.Store", return_value=backend
    ):
        store = ChoreRaceStore(hass)

        with pytest.raises(ValueError, match="Cannot save unsupported"):
            await store.async_save(ChoreRaceData(schema_version=2))

    backend.async_save.assert_not_awaited()
