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

## Admin mutations

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
