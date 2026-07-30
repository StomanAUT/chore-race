"""Clean-install smoke test for a fresh Home Assistant config entry."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chore_race.const import DOMAIN


async def test_clean_install_creates_and_unloads_all_sensors(hass):
    """A new empty installation loads without seed data or existing storage."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Chore Race",
        data={},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert {entity.unique_id for entity in entities} == {
        "chore_race_open_tasks",
        "chore_race_completed_today",
        "chore_race_automatic_tasks_today",
        "chore_race_week_leader",
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
