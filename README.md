# Chore Race

Chore Race is a local-first Home Assistant household planner that will grow
into a family-friendly, gamified 30-minute chore race. The current 0.7
milestone adds idempotent automation and entity helpers to the planner
foundation: participants linked to Home Assistant persons, reusable chore
types, dated and recurring tasks, completions, undo, scoring history, aggregate
sensors and planner and race cards.

> Early development: storage schema and APIs may still change before 1.0.

## Installation

### HACS

1. Add `https://github.com/StomanAUT/chore-race` as a custom HACS integration
   repository.
2. Install **Chore Race** and restart Home Assistant.
3. Add **Chore Race** from **Settings → Devices & services → Add integration**.

### Manual

Copy `custom_components/chore_race` into the Home Assistant configuration
directory and restart Home Assistant. Add **Chore Race** from **Settings →
Devices & services → Add integration**. Configuration through
`configuration.yaml` is not supported. Only one instance is allowed.

The integration does not create household-specific seed data. Participants and
chore types are created through Actions or the planner, so names, rooms and
point values remain fully configurable.

## Core rules

- Tasks are free for any active participant. A preferred participant is only
  metadata.
- Outside a race, every completion awards exactly one configurable normal point.
- A task snapshots its race points when it is created.
- A completion snapshots every point component actually awarded.
- One concrete task can have only one active completion.
- Undo keeps the completion as a reverted audit record and reopens the task.
- Team progress counts completed tasks, not points.
- Home Assistant Area Registry IDs are referenced instead of duplicating rooms.
- Recurrence rules support intervals in days as well as monthly and yearly
  schedules.

## Actions

Management actions require a Home Assistant administrator when called by a
logged-in user. Calls from trusted Home Assistant automations have no user
context and remain supported.

- `chore_race.create_participant`
- `chore_race.update_participant`
- `chore_race.create_chore_type`
- `chore_race.update_chore_type`
- `chore_race.delete_chore_type`
- `chore_race.create_task`
- `chore_race.ensure_task`
- `chore_race.update_task`
- `chore_race.create_recurrence_rule`
- `chore_race.complete_task`
- `chore_race.undo_completion`
- `chore_race.delete_task`

Action calls can request response data to retrieve the generated stable IDs.
`chore_race.ensure_task` is intended for automations and entity integrations:
retries with the same deduplication key return the existing task instead of
creating duplicates.

## Entities and API

The integration exposes open tasks today, completed tasks today, automatically
created tasks today and the current week leader as event-driven sensors. Large
task collections are deliberately not placed in entity attributes.

Authenticated read-only WebSocket commands:

- `chore_race/get_state`
- `chore_race/get_tasks`
- `chore_race/get_participants`
- `chore_race/get_chore_types`
- `chore_race/get_leaderboard`
- `chore_race/get_areas`
- `chore_race/get_settings`

Admin-only planner commands:

- `chore_race/create_participant`
- `chore_race/update_participant`
- `chore_race/create_chore_type`
- `chore_race/update_chore_type`
- `chore_race/delete_chore_type`
- `chore_race/create_task`
- `chore_race/update_task`
- `chore_race/delete_task`
- `chore_race/create_recurrence_rule`
- `chore_race/update_settings`

These commands are the stable backend boundary for the adult planner. They use
Home Assistant authentication and its built-in admin permission checks rather
than a parallel account or role system.

## Architecture

`models.py` owns serialization-safe domain records, `storage.py` wraps the
versioned Home Assistant `Store`, `scoring.py` is the single scoring policy,
and `manager.py` owns validated atomic mutations and aggregation. Home
Assistant actions, WebSocket commands and sensors are adapters around that
manager. No polling coordinator is used because all changes are local events.

Storage reserves versioned top-level collections for race sessions, recurrence
rules, task chains and rewards. Completion records reserve separate driver,
copilot, fair-play and streak snapshots. Race scoring will enforce the product
rule that copilot and fair-play cannot both apply.

See [docs/architecture.md](docs/architecture.md) and
[docs/planner-api.md](docs/planner-api.md) for the current semantics and API.

## Development

The test suite targets a Home Assistant development environment with
`pytest-homeassistant-custom-component`. Run:

```text
pytest
ruff check .
```

Tests must use a separate temporary Home Assistant configuration and must never
run against a production configuration.

## Roadmap

1. 0.2 Planner UI and recurring tasks
2. 0.3 Race engine and race scoring
3. 0.4 Child-friendly tablet card
4. 0.5 Rewards
5. 0.6 Recurring tasks
6. 0.7 Automation/entity helpers (current development branch)
7. 0.8 General task chains (next)
8. 1.0 Stable public family release
