# Chore Race card animation prototype

This directory contains an **experimental, dependency-free** Lovelace card
prototype. It is deliberately not bundled, copied, registered, or installed by
the Chore Race integration.

The card visualizes:

- responsive participant lanes with transform-based car movement;
- weekly points from the existing `chore_race/get_leaderboard` command;
- team task progress from the existing `chore_race/get_state` command;
- participant metadata from `chore_race/get_participants`;
- automatic and configurable reduced-motion behavior;
- safe connection cleanup, bounded refresh intervals, stale-request rejection,
  and last-known-state display when an API call fails.

No backend contract or storage data is changed.

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
as a module resource, and add:

```yaml
type: custom:chore-race-planner-card
title: Chore Race Planer
max_width: 960
accent_color: "#74829a"
```

The planner guides an administrator through creating a participant, a reusable
chore type, and then a dated or recurring task. Recurring schedules support
every N days, monthly, and yearly patterns. Existing chore types and open tasks
are listed below the forms. The icon picker provides a curated visual selection
without requiring Material Design Icon names.

Both cards accept a `max_width` between 360 and 1400 pixels and an optional
six-digit hexadecimal `accent_color`. They always shrink to the available
mobile width.

`refresh_interval` is clamped to 10-300 seconds. Set
`force_reduced_motion: true` to disable animation regardless of the operating
system preference.

## Prototype boundaries

- Read-only; it does not complete tasks or mutate Home Assistant.
- Uses only the v0.1 WebSocket commands.
- Does not yet subscribe to push events; it refreshes while connected and
  visible.
- Styling and the points-to-distance mapping are experimental.
