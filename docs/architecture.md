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

## Daily plan semantics

- `completed_tasks_today()` counts completions by their completion timestamp.
- `completed_scheduled_tasks_today()` counts completed tasks planned for today.
- `open_tasks_today()` counts unblocked, open tasks planned for today.

The compact card state uses scheduled-task counts for plan progress and keeps
completion-timestamp counts as a separate manager API.

## Chore artwork

`ChoreType.image` is the primary visual used by the planner and race card.
The normal planner UI therefore exposes only the curated task-image library.
`ChoreType.icon` remains optional in storage and APIs as a compatibility
fallback for older records, Home Assistant automations, and installations
whose image asset is temporarily unavailable.
