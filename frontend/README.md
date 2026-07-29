# Chore Race Lovelace cards

This directory contains the dependency-free race and planner Lovelace cards.
They are currently installed as manual Home Assistant resources while the
packaging flow is still being stabilized.

The card visualizes and operates:

- responsive participant lanes with transform-based car movement;
- weekly points from the existing `chore_race/get_leaderboard` command;
- team task progress from the existing `chore_race/get_state` command;
- participant metadata from `chore_race/get_participants`;
- today's open race tasks as responsive image-first cards;
- a touch-friendly participant picker for completing a task during a race;
- immediate task and leaderboard refresh after a successful completion;
- automatic and configurable reduced-motion behavior;
- safe connection cleanup, bounded refresh intervals, stale-request rejection,
  and last-known-state display when an API call fails.

## Local preview

From the repository root, serve the files with any static HTTP server:

```text
python -m http.server 8080 --directory frontend
```

Then open `http://localhost:8080/demo.html`. The demo has local controls for
points, completed tasks, and reduced motion. When no Home Assistant object is
provided, the custom element also renders built-in demo data.

## Optional manual Home Assistant preview

This is intentionally manual and should only be used on a development
dashboard:

1. Copy `chore-race-card.js` into the Home Assistant `www` directory.
2. Add `/local/chore-race-card.js` as a JavaScript module dashboard resource.
3. Add a manual card:

```yaml
type: custom:chore-race-card
title: Familien Grand Prix
target_points: 12
refresh_interval: 30
max_width: 820
accent_color: "#74829a"
```

For the admin-only planner, also copy `chore-race-planner-card.js`, register it
as a module resource, and copy
`custom_components/chore_race/task_icons/` to
`config/www/chore-race-icons/`. Then add:

```yaml
type: custom:chore-race-planner-card
title: Chore Race Planer
max_width: 960
accent_color: "#74829a"
```

The planner guides an administrator through creating a participant, a reusable
chore type, and then a dated or recurring task. Recurring schedules support
every N days, monthly, and yearly patterns. Existing chore types and open tasks
use compact, expandable edit panels. The image picker stays collapsed until it
is needed and provides a curated visual selection without requiring Material
Design Icon names.

Both cards expose `max_width` and `accent_color` in Home Assistant's visual
card editor. `max_width` accepts 280 to 1400 pixels; the cards also shrink to
the available dashboard column width.

`refresh_interval` is clamped to 10-300 seconds. Set
`force_reduced_motion: true` to disable animation regardless of the operating
system preference.

## Race completion flow

While `chore_race/get_race_state` reports `running`, each open task exposes an
**Erledigt** action. It opens a participant picker and calls
`chore_race/complete_race_task`. The backend remains authoritative for active
race state, participant permissions, adult-only chores, duplicate completion,
scoring, and persistence. Ready and finished races never show a misleading
completion button.

Administrators can start a ready race or a new race after the previous finish
directly from the card. During a running race they also receive a quiet
secondary stop action that requires confirmation. Both actions use the
admin-protected `chore_race/start_race` and `chore_race/stop_race` WebSocket
commands.

Task images are the primary visual. The configured Material Design icon is
used only when a chore type has no image. Area IDs are resolved through Home
Assistant's Area Registry. For adult-only chores, children without the explicit
restricted-task permission remain visible in the picker but cannot be selected.
Legacy `/chore-race-assets/` image paths are mapped to
`/local/chore-race-icons/`, and task artwork is fitted without cropping.

## Prototype boundaries

- Household-level mutations are limited to completing tasks during an active
  race.
- Race start and stop controls are visible only to Home Assistant admins.
- Does not yet subscribe to push events; it refreshes while connected and
  visible.
- Styling and the points-to-distance mapping are experimental.
