# Planner API

Milestone 0.2 starts with an authenticated planner boundary that can be used by
a future Home Assistant panel or Lovelace editor without duplicating business
logic in JavaScript.

Read commands are available to every authenticated Home Assistant connection.
Mutating planner commands use Home Assistant's `require_admin` WebSocket guard.

## Read

| Command | Result |
| --- | --- |
| `chore_race/get_participants` | Stable participant records |
| `chore_race/get_chore_types` | Reusable chore definitions |
| `chore_race/get_tasks` | Concrete task snapshots |
| `chore_race/get_areas` | Current HA Area Registry records |
| `chore_race/get_settings` | Planner and race-ready settings |
| `chore_race/get_state` | Compact team/today state |
| `chore_race/get_leaderboard` | Current-week totals |
| `chore_race/get_race_state` | Current/latest race, countdown, open tasks and leaderboard |
| `chore_race/get_recurrence_rules` | Persisted recurrence rules |

## Authenticated race completion

Any authenticated household dashboard may report a task completed during an
active race:

```json
{
  "type": "chore_race/complete_race_task",
  "task_id": "stable-task-id",
  "participant_id": "stable-participant-id"
}
```

The response is the refreshed race state. The server rejects inactive
participants, adult-only permission violations, blocked or already completed
tasks, and requests made without a running race.

## Admin mutations

Race lifecycle mutations are admin-only:

```json
{"type": "chore_race/start_race"}
```

```json
{"type": "chore_race/stop_race"}
```

### Create a participant

```json
{
  "type": "chore_race/create_participant",
  "name": "Arthur",
  "sort_order": 30
}
```

### Create a chore type

```json
{
  "type": "chore_race/create_chore_type",
  "name": "Aufräumen",
  "icon": "mdi:broom",
  "default_race_points": 5,
  "streak_enabled": true,
  "streak_max_bonus": 3
}
```

### Create a dated task

```json
{
  "type": "chore_race/create_task",
  "chore_type_id": "stable-type-id",
  "date": "2026-07-28",
  "area_id": "kinderzimmer_arthur",
  "preferred_participant_id": "stable-participant-id"
}
```

### Update an open task

```json
{
  "type": "chore_race/update_task",
  "task_id": "stable-task-id",
  "date": "2026-07-30",
  "area_id": "wohnzimmer",
  "preferred_participant_id": "stable-participant-id",
  "race_points": 4
}
```

Only untouched open tasks can be updated or deleted. Tasks with completion
history remain immutable, including after an undo. Tasks scheduled for today
are also locked while a race is running.

Chore types can be updated through `chore_race/update_chore_type`. Permanent
deletion through `chore_race/delete_chore_type` is allowed only when no task or
recurrence rule references the type; otherwise it must be deactivated.

### Update settings

```json
{
  "type": "chore_race/update_settings",
  "race_enabled": true,
  "race_duration_seconds": 1800,
  "race_weekdays": [0, 1, 2, 3, 4],
  "race_ready_time": "19:00"
}
```

Settings persist through Home Assistant's versioned integration store. Race
configuration is exposed now, but Milestone 0.2 does not start a race or run a
timer.
