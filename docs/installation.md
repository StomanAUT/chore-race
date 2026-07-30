# Installation and upgrades

## HACS

1. Open HACS in Home Assistant.
2. Add `https://github.com/StomanAUT/chore-race` as a custom **Integration**
   repository.
3. Install **Chore Race** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration**, search for
   **Chore Race**, and finish the one-step setup.

Tagged releases use semantic versions such as `v1.0.0`. HACS downloads the
matching `chore_race.zip` release asset and shows available upgrades.

## Manual installation

Copy `custom_components/chore_race` to the same path below the Home Assistant
configuration directory and restart Home Assistant. Do not add Chore Race to
`configuration.yaml`; it is configured through the UI.

The two dashboard cards are currently installed as manual resources:

1. Copy `frontend/chore-race-card.js` and
   `frontend/chore-race-planner-card.js` to `config/www/`.
2. Copy `custom_components/chore_race/task_icons/` to
   `config/www/chore-race-icons/`.
3. Under **Settings → Dashboards → Resources**, add both files as JavaScript
   modules:

   - `/local/chore-race-card.js?v=100`
   - `/local/chore-race-planner-card.js?v=100`

Increase the query value after replacing a card file so browsers fetch the new
version.

## Safe upgrade

1. Create a full Home Assistant backup.
2. Install the new version through HACS or replace the manual files.
3. Run Home Assistant's configuration check.
4. Restart Home Assistant.
5. Confirm that the integration loads and open both Chore Race views.

Chore Race migrates its versioned store when loading. Never edit files below
`config/.storage` while Home Assistant is running.

## Rollback

Restore the full Home Assistant backup created immediately before the upgrade.
For a manual card-only rollback, restore the previous JavaScript files, change
their resource query value, and reload the browser.

## Release clean-install gate

Every pull request creates the same `chore_race.zip` file consumed by HACS,
extracts it into a new temporary `config/custom_components/chore_race`
directory, validates its paths and manifest, and compiles every included
Python file. The Home Assistant test suite additionally creates a new Chore
Race config entry with empty storage, verifies all four aggregate sensors, and
unloads the integration again.

Run the package gate locally with:

```text
python scripts/release_package.py build chore_race.zip
python scripts/release_package.py validate chore_race.zip
```
