# Planner API

Milestone 0.2 starts with an authenticated planner boundary that can be used by
a future Home Assistant panel or Lovelace editor without duplicating business
logic in JavaScript.

Read commands are available to every authenticated Home Assistant connection.
Mutating planner commands use Home Assistant's `require_admin` WebSocket guard.

## Permissions and errors

All WebSocket commands require an authenticated Home Assistant connection.
Planner writes and race lifecycle changes (`start`, `stop`, `reset`, participant
removal) additionally require an administrator. Task completion and the
champion's reward selection deliberately remain available to any authenticated
household dashboard.

Service calls from a user context follow the same split: every management
action requires an administrator, while `chore_race.complete_task` is available
to an authenticated household user. Calls without a user context are trusted
Home Assistant automation/internal calls.

Failures use stable machine-readable codes. Clients should branch on `code` and
treat the human-readable message as display text:

| Code | Meaning |
| --- | --- |
| `not_loaded` | The integration has no loaded config entry |
| `not_found` | A referenced Chore Race record does not exist |
| `conflict` | The request conflicts with current or historical state |
| `validation_error` | The request violates a domain rule |
| `chore_race_error` | Fallback for an otherwise unclassified domain failure |

The same domain codes are exposed as Home Assistant service validation
translation keys. Authentication/authorization failures continue to use Home
Assistant's native unauthorized error contract.

## Read

| Command | Result |
| --- | --- |
| `chore_race/get_participants` | Stable participant records |
| `chore_race/get_chore_types` | Reusable chore definitions |
| `chore_race/get_tasks` | Concrete task snapshots |
| `chore_race/get_areas` | Current HA Area and Floor Registry records (`kind`) |
| `chore_race/get_floors` | Current HA Floor Registry records |
| `chore_race/get_settings` | Planner and race-ready settings |
| `chore_race/get_state` | Compact team/today state |
| `chore_race/get_leaderboard` | Current-week totals |
| `chore_race/get_race_state` | Current/latest race, countdown, open tasks and leaderboard |
| `chore_race/get_recurrence_rules` | Persisted recurrence rules |
| `chore_race/get_task_chains` | Chain definitions, steps and materialized task state |

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

Reset the current race, or pass `race_id` to reset a selected session:

```json
{
  "type": "chore_race/reset_race",
  "race_id": "optional-race-id"
}
```

The session remains auditable with status `ready` and a `reset_at` timestamp.
Only active completions belonging to that race are reverted and their tasks
reopened. Normal points and points from other races are preserved.

Remove a participant from the current race, or from a selected session:

```json
{
  "type": "chore_race/remove_race_participant",
  "participant_id": "stable-participant-id",
  "race_id": "optional-race-id"
}
```

This changes only the session's `participant_ids`; the global participant
record remains active. Active completions in that race involving the removed
participant as driver or copilot are reverted and their tasks reopened.
Unrelated completions remain active.

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

Tasks may target either one Home Assistant area (`area_id`) or one Home
Assistant floor (`floor_id`). The fields are mutually exclusive. Omit both for
a household-wide task. `race_points`, when supplied, is the base value per
room. For a floor assignment the manager multiplies it (or the chore type's
default) by the number of Home Assistant areas currently assigned to the
floor. The response exposes `base_race_points`, `points_multiplier`, and the
final `race_points`.

```json
{
  "type": "chore_race/create_task",
  "chore_type_id": "stable-type-id",
  "date": "2026-07-28",
  "floor_id": "erdgeschoss",
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
  "floor_id": null,
  "preferred_participant_id": "stable-participant-id",
  "race_points": 4
}
```

When changing the scope, clear the previous field explicitly: for example,
send `area_id: null` together with a new `floor_id`. The manager validates IDs
against Home Assistant's registries and rejects requests containing both.
Changing an open task's location or base `race_points` recalculates its
snapshotted total. A floor without assigned rooms is rejected.

Only untouched open tasks can be updated or deleted. Tasks with completion
history remain immutable, including after an undo. Untouched open tasks remain
editable during a running race, and the live race queue reflects changes
immediately.

Chore types can be updated through `chore_race/update_chore_type`. Permanent
deletion through `chore_race/delete_chore_type` is allowed only when no task or
recurrence rule references the type; otherwise it must be deactivated.

### Create and manage task chains

Task chains unlock later chores only after their dependencies have been
completed. Step IDs are stable within a chain and dependencies refer to those
IDs. Multiple dependencies provide fan-in semantics: the step remains blocked
until every predecessor is complete.

```json
{
  "type": "chore_race/create_task_chain",
  "name": "Küche komplett",
  "task_date": "2026-07-30",
  "steps": [
    {
      "id": "clear",
      "chore_type_id": "clear-counter",
      "depends_on": []
    },
    {
      "id": "wipe",
      "chore_type_id": "wipe-counter",
      "depends_on": ["clear"]
    },
    {
      "id": "floor",
      "chore_type_id": "mop-floor",
      "depends_on": ["wipe"]
    }
  ]
}
```

Administrators may update an unused definition with
`chore_race/update_task_chain` and remove it with
`chore_race/delete_task_chain`. A chain with completion history is immutable,
so historical results cannot silently change. Deactivating an unused chain
removes its untouched materialized tasks; activating it again materializes its
root steps.

```json
{
  "type": "chore_race/update_task_chain",
  "chain_id": "stable-chain-id",
  "name": "Küche am Abend",
  "active": true
}
```

```json
{
  "type": "chore_race/delete_task_chain",
  "chain_id": "stable-chain-id"
}
```

Completing or undoing a chain task automatically reconciles all successors.
The race view exposes chain progress and never allows a blocked task to be
completed.

### Ensure a task from an automation or entity

Home Assistant automations and entity integrations should call the
`chore_race.ensure_task` action instead of `create_task`. It accepts the same
location, participant and point fields, plus:

- `source`: `automation` (default) or `entity`;
- `source_entity_id`: required owner or triggering entity;
- `deduplication_key`: optional stable identity for one external event.

Without an explicit key, Chore Race derives one from source, source entity,
chore type, task date and location. Repeating the action then returns the same
task. An explicit key is preferable when multiple distinct events may occur on
one day. The action response contains `created` and the complete `task` record.

```yaml
automation:
  - alias: "Chore Race: Waschmaschine ist fertig"
    triggers:
      - trigger: state
        entity_id: sensor.washing_machine_state
        to: "finished"
    actions:
      - action: chore_race.ensure_task
        response_variable: chore_race_result
        data:
          chore_type_id: "stable-type-id"
          source: entity
          source_entity_id: "{{ trigger.entity_id }}"
          area_id: "utility_room"
          deduplication_key: >-
            {{ trigger.entity_id }}:{{ trigger.to_state.last_changed.isoformat() }}
```

If the automation is replayed for the same state change,
`chore_race_result.created` is `false` and no duplicate is added. Omitting
`date` schedules the task for today in Home Assistant's configured timezone.
`area_id` and `floor_id` remain mutually exclusive.

Every newly created task fires this Home Assistant event:

```yaml
event_type: chore_race_task_created
data:
  task_id: "stable-task-id"
  source: entity
  source_entity_id: sensor.washing_machine_state
```

An idempotent repeat call does not emit the event again. The
`automatic_tasks_today` sensor and `chore_race/get_state` field report how many
non-cancelled entity or automation tasks were created on the current local
day.

Recurring rules accept the same mutually exclusive `area_id` and `floor_id`
fields. Every materialized task snapshots that assignment, so a rule such as
“Boden wischen · Erdgeschoss · 1 Punkt pro Raum” produces one floor-wide task
per due date and snapshots the then-current room multiplier.

`frequency` accepts `days`, `weekdays`, `monthly`, `yearly` and
`completion_interval`. Weekday rules include a `weekdays` array using Monday
`0` through Sunday `6`. Completion intervals use `interval` as the number of
local calendar days after the last active completion and suppress new
materialization while an earlier generated task remains open.

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
configuration is also consumed by the Milestone 0.3 race engine.

## Race WebSocket API

Administrators start and stop a session with:

```json
{"type": "chore_race/start_race"}
```

```json
{"type": "chore_race/stop_race"}
```

They can also reset the current or selected session and remove a participant
from its local roster:

```json
{"type": "chore_race/reset_race", "race_id": "optional-race-id"}
```

```json
{
  "type": "chore_race/remove_race_participant",
  "participant_id": "participant-id",
  "race_id": "optional-race-id"
}
```

During a running race an authenticated client completes a task with optional
teamwork scoring:

```json
{
  "type": "chore_race/complete_race_task",
  "task_id": "task-id",
  "participant_id": "driver-id",
  "copilot_participant_id": "optional-copilot-id",
  "fair_play": false
}
```

`copilot_participant_id` and `fair_play: true` cannot be combined. The result
is the updated race state including countdown, open tasks, a ranked scoring
breakdown, the most recent completion and the champion after a unique win.

## Reward API

The planner reads and manages the ordered reward catalog through
`chore_race/get_rewards`, `chore_race/create_reward`,
`chore_race/update_reward` and `chore_race/delete_reward`. Mutations require a
Home Assistant administrator.

After a finished race, the shared household tablet records the unique
champion's one-time choice with:

```json
{
  "type": "chore_race/select_reward",
  "race_id": "race-id",
  "reward_id": "reward-id"
}
```

The backend derives the champion, rejects ties, non-positive results, active
races, inactive rewards and repeat selections.
