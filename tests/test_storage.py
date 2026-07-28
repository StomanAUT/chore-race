"""Storage adapter restart test."""

from unittest.mock import AsyncMock, patch

from custom_components.chore_race.models import ChoreRaceData, Participant
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
