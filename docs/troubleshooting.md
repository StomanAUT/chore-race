# Troubleshooting

## `Unknown command` or `Service ... not found`

The frontend and integration are on different versions.

1. Confirm the installed version in
   `custom_components/chore_race/manifest.json`.
2. Restart Home Assistant after replacing the integration.
3. Increase the `?v=` value of both dashboard resources.
4. Reload the browser without cache.

## The card still shows the old layout

Home Assistant and the browser cache JavaScript resources aggressively. Check
**Settings → Dashboards → Resources** and use a new query value, for example
`/local/chore-race-card.js?v=101`.

## Configuration error after an upgrade

Run Home Assistant's configuration check before restarting. If Chore Race does
not load, inspect **Settings → System → Logs** for `chore_race` and restore the
pre-upgrade backup if necessary.

## `lovelace_resources` storage damage

Do not acknowledge the repair until a valid resource store has been restored.
Prefer restoring the full Home Assistant backup. Advanced manual recovery must
be done while Home Assistant Core is stopped and the resulting JSON must be
parsed successfully before Core is started again. A UTF-8 byte-order mark or
an empty first byte causes the `line 1 column 1` error.

## A task cannot be edited or deleted

Tasks and task chains with completion history are intentionally immutable.
Undo preserves an audit record, so it does not make the record deletable.
Create a corrected task or chain and deactivate the old definition.

## Where to report a bug

Open an issue at <https://github.com/StomanAUT/chore-race/issues> and include:

- Home Assistant and Chore Race versions;
- the exact action or WebSocket error;
- relevant `chore_race` log lines;
- whether the issue persists after a restart and cache refresh.
