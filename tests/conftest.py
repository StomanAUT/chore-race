"""Shared Chore Race tests."""

from unittest.mock import AsyncMock

import pytest

from custom_components.chore_race.manager import ChoreRaceManager
from custom_components.chore_race.models import ChoreRaceData


@pytest.fixture
def manager(hass):
    """Return a manager backed by an in-memory mocked store."""
    store = AsyncMock()
    store.async_load.return_value = ChoreRaceData()
    return ChoreRaceManager(hass, store)
