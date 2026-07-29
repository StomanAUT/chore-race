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

## Race lifecycle

A session moves from `ready` to `running` and finally `finished`. Only one
non-expired session can run at a time. Start and stop are administrator-only
WebSocket commands, while authenticated household clients may complete an open
task during a running session. Expired sessions are presented as finished and
are closed persistently when the next session starts.

## Daily plan semantics

- `completed_tasks_today()` counts completions by their completion timestamp.
- `completed_scheduled_tasks_today()` counts completed tasks planned for today.
- `open_tasks_today()` counts unblocked, open tasks planned for today.

The compact card state uses scheduled-task counts for plan progress and keeps
completion-timestamp counts as a separate manager API.

## Task location scope

A concrete task and a recurrence rule can optionally reference one Home
Assistant Area Registry entry (`area_id`) or one Floor Registry entry
(`floor_id`). These fields are mutually exclusive:

- an area scopes work to a single room;
- a floor scopes work across all rooms on that floor;
- neither field means the task has no location scope.

Registry IDs remain the stable stored identity; names and icons are resolved
for presentation. Existing records without `floor_id` continue to load with
the default value `null`. Materialized recurring tasks snapshot the rule's
location scope so later rule edits do not rewrite existing work or history.

## Chore artwork

`ChoreType.image` is the primary visual used by the planner and race card.
The normal planner UI therefore exposes only the curated task-image library.
`ChoreType.icon` remains optional in storage and APIs as a compatibility
fallback for older records, Home Assistant automations, and installations
whose image asset is temporarily unavailable.
