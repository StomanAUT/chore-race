"""Versioned Home Assistant storage adapter for Chore Race."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import ChoreRaceData

LOGICAL_SCHEMA_VERSION = 1


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
        if data.schema_version != LOGICAL_SCHEMA_VERSION:
            raise ValueError(
                "Cannot save unsupported Chore Race schema version: "
                f"{data.schema_version}"
            )
        await self._store.async_save(data.to_dict())

    @staticmethod
    def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
        """Migrate logical schema versions independently of Store format."""
        if not isinstance(raw, dict):
            raise ValueError("Chore Race storage root must be a dictionary")
        version = raw.get("schema_version", 1)
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError(
                "Chore Race schema version must be an integer, got "
                f"{version!r}"
            )
        if version != LOGICAL_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Chore Race schema version: {version}")

        # Copy the root before normalizing it: Home Assistant may retain the
        # object returned by Store, and migration must never mutate that input.
        migrated = dict(raw)
        migrated["schema_version"] = LOGICAL_SCHEMA_VERSION
        for collection_name in (
            "participants",
            "chore_types",
            "tasks",
            "completions",
            "race_sessions",
            "recurrence_rules",
            "task_chains",
            "rewards",
            "reward_selections",
        ):
            migrated.setdefault(collection_name, {})
        migrated.setdefault("settings", {})
        return migrated
