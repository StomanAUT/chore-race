"""Sensor platform for Chore Race."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .manager import ChoreRaceManager


@dataclass(frozen=True, kw_only=True)
class ChoreRaceSensorDescription(SensorEntityDescription):
    """Describe one aggregate sensor."""

    value_fn: Callable[[ChoreRaceManager], Any]


SENSORS = (
    ChoreRaceSensorDescription(
        key="open_tasks",
        translation_key="open_tasks",
        icon="mdi:clipboard-list-outline",
        native_unit_of_measurement="tasks",
        value_fn=lambda manager: manager.open_tasks_today(),
    ),
    ChoreRaceSensorDescription(
        key="completed_today",
        translation_key="completed_today",
        icon="mdi:clipboard-check-outline",
        native_unit_of_measurement="tasks",
        value_fn=lambda manager: manager.completed_tasks_today(),
    ),
    ChoreRaceSensorDescription(
        key="week_leader",
        translation_key="week_leader",
        icon="mdi:trophy-outline",
        value_fn=lambda manager: (
            manager.week_leader().name if manager.week_leader() else "none"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ChoreRaceManager],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up stable aggregate sensors."""
    async_add_entities(
        ChoreRaceSensor(entry.runtime_data, description)
        for description in SENSORS
    )


class ChoreRaceSensor(SensorEntity):
    """An event-driven Chore Race aggregate."""

    entity_description: ChoreRaceSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        manager: ChoreRaceManager,
        description: ChoreRaceSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        self._manager = manager
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._remove_listener: Callable[[], None] | None = None

    @property
    def native_value(self) -> Any:
        """Return the current aggregate."""
        return self.entity_description.value_fn(self._manager)

    async def async_added_to_hass(self) -> None:
        """Subscribe to local manager updates."""
        await super().async_added_to_hass()
        self._remove_listener = self._manager.async_add_listener(
            self._handle_manager_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe on unload."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_manager_update(self) -> None:
        self.async_write_ha_state()
