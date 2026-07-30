# Chore Race architecture

## Participant permissions

Participants are independent from Home Assistant users. Every participant has a
`role` of `child` or `adult`; existing records migrate implicitly to `child`.
`can_do_restricted_tasks` is an explicit exception. A chore type marked
`adult_only` can only be completed by an adult or by a participant carrying
that exception. The manager enforces this rule, so every service and UI follows
the same policy.

## Point semantics

- `points_week_all()` includes every active completion in the current ISO week.
- `race_points_week(race_id=None)` includes only race-scored completions and can
  optionally be restricted to one race.
- `normal_points_week()` includes only normal completions.
- Champion and race leaderboard calculations exclusively use race points.

## Race scoring

Race completion snapshots are additive and auditable:

- The driver receives the task's snapshotted race points.
- Fair play adds the configured household bonus to the driver.
- A copilot receives the chore type's configured copilot points separately.
- Fair play and copilot are mutually exclusive for one completion.
- When enabled on the chore type, the driver's consecutive completions in the
  same race add `0, 1, 2, ...` streak points up to the configured maximum.
- Driver and copilot must be different active participants. Restricted chores
  enforce their participant permission for both roles.

The live leaderboard aggregates exactly one race session, not a calendar-week
window. It exposes base, fair-play, streak and copilot subtotals. A finished
race has a champion only when one participant holds a unique positive lead;
ties deliberately produce no champion.

## Rewards

Administrators maintain a small ordered reward catalog. A reward can be
deactivated without changing history. After a finished race, only a unique
champion with positive race points can make one reward selection. The manager
derives that participant from the authoritative race leaderboard; clients
never submit a winner identity.

The selection is immutable, belongs to one stable race ID and snapshots the
selected reward and participant IDs with its timestamp. Used rewards cannot be
deleted, only deactivated. Race state exposes the current selection and the
most recent household winner choice for the tablet card.

## Race lifecycle

A session moves from `ready` to `running` and finally `finished`. Only one
non-expired session can run at a time. Start and stop are administrator-only
WebSocket commands, while authenticated household clients may complete an open
task during a running session. Expired sessions are presented as finished and
are closed persistently when the next session starts.

Each session snapshots `participant_ids` from the active household
participants when it starts. This is a race-local roster: removing somebody
from a race never deactivates or deletes their global participant record.

Administrators may reset the current race or select a session by `race_id`. A
reset keeps the session for audit, sets it back to `ready`, records `reset_at`,
and rebuilds its roster from the participants that are currently globally
active. Only active completions whose `race_id` matches that session are
reverted, and their tasks are reopened. Normal completions and completions from
every other race remain active and keep their points.

Removing a participant from a selected race removes their ID from that
session's roster. Any active completion in that race where the participant was
the driver or copilot is reverted as one immutable scoring unit, and its task
is reopened. Other participants' unrelated completions remain active. The
operation is available for running, finished, and reset/ready sessions.

## Daily plan semantics

- `completed_tasks_today()` counts completions by their completion timestamp.
- `completed_scheduled_tasks_today()` counts completed tasks planned for today.
- `open_tasks_today()` counts unblocked, open tasks planned for today.
- `automatic_tasks_today()` counts non-cancelled entity and automation tasks by
  their local creation date.

The compact card state uses scheduled-task counts for plan progress and keeps
completion-timestamp counts as a separate manager API.

## Automation and entity task identity

`ensure_task` is the idempotent boundary for tasks originating outside the
planner. It accepts only the `entity` and `automation` task sources and always
requires `source_entity_id`, so every generated task remains attributable to
the Home Assistant entity or automation that requested it.

Callers may supply a stable `deduplication_key` for one physical event. When it
is omitted, the manager derives a daily key from source, source entity, chore
type, task date and location. The lookup and creation share the manager's
mutation lock, so concurrent retries cannot create duplicates. The action
returns `created: true` with the new task or `created: false` with the
previously stored task.

A newly persisted task fires `chore_race_task_created` with `task_id`, `source`
and `source_entity_id`. An idempotent retry does not fire a second event. The
`automatic_tasks_today` sensor counts tasks whose source is `entity` or
`automation` and whose `created_at` falls on the current local date; cancelled
tasks are excluded.

## Task location scope

A concrete task and a recurrence rule can optionally reference one Home
Assistant Area Registry entry (`area_id`) or one Floor Registry entry
(`floor_id`). These fields are mutually exclusive:

- an area scopes work to a single room;
- a floor scopes work across all rooms on that floor;
- neither field means the task has no location scope.

Point defaults are interpreted per room. A floor-wide task snapshots the
current number of Home Assistant areas assigned to that floor and stores:

- `base_race_points`: the chore type's points per room;
- `points_multiplier`: the number of rooms when the task was planned;
- `race_points`: the resulting total.

For example, a one-point chore covering six rooms snapshots `1 × 6 = 6`
points. Later registry or chore-type changes do not silently rewrite that
task's value. Floors without assigned rooms are rejected instead of creating
an ambiguous zero-room task.

Registry IDs remain the stable stored identity; names and icons are resolved
for presentation. Existing records without `floor_id` continue to load with
the default value `null`. Materialized recurring tasks snapshot the rule's
location scope so later rule edits do not rewrite existing work or history.

## Recurrence semantics

Calendar rules support every N days, selected weekdays, monthly and yearly
dates. Monthly and yearly rules that begin at the end of a month use that
month's final valid day.

Completion-based rules create their first task on or after the configured
start date. They never create another instance while generated work remains
open. After completion, the next task becomes due only after the configured
number of local calendar days. The completion timestamp is authoritative;
changing the rule never rewrites already materialized tasks or history.

## Chore artwork

`ChoreType.image` is the primary visual used by the planner and race card.
The normal planner UI therefore exposes only the curated task-image library.
`ChoreType.icon` remains optional in storage and APIs as a compatibility
fallback for older records, Home Assistant automations, and installations
whose image asset is temporarily unavailable.
