"""Versioned Home Assistant storage adapter for Chore Race."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import ChoreRaceData


class ChoreRaceStore:
    """Keep persistence details outside business logic."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            minor_version=0,
            serialize_in_event_loop=False,
        )

    async def async_load(self) -> ChoreRaceData:
        """Load and migrate storage."""
        raw = await self._store.async_load()
        if raw is None:
            return ChoreRaceData()
        return ChoreRaceData.from_dict(self._migrate(raw))

    async def async_save(self, data: ChoreRaceData) -> None:
        """Persist a consistent snapshot."""
        await self._store.async_save(data.to_dict())

    @staticmethod
    def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
        """Migrate logical schema versions independently of Store format."""
        version = raw.get("schema_version", 1)
        if version != 1:
            raise ValueError(f"Unsupported Chore Race schema version: {version}")
        migrated = dict(raw)
        # v1 originally reserved this collection as untyped dictionaries.
        # The model loader accepts those legacy records and canonicalizes them
        # when the next snapshot is saved.
        migrated.setdefault("task_chains", {})
        return migrated
