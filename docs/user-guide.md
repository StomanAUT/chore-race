# Chore Race user guide

[Deutsch](bedienungsanleitung.md) · [Project overview](../README.md)

This guide describes the features currently available in Chore Race 0.8. The
labels below follow the cards' current German user interface.

## 1. Installation

Install the integration, both JavaScript cards, and the task artwork by
following [Installation and upgrades](installation.md). Restart Home Assistant
after changing the integration. When updating card files, change their `?v=`
resource query and reload the browser without cache.

Add one `custom:chore-race-planner-card` for administration and one
`custom:chore-race-card` for daily use and races. Both cards support a
configurable `max_width` and `accent_color`; see
[Configuration examples](examples.md).

Only Home Assistant administrators may use the planner's write operations and
race controls.

## 2. Initial setup

Before using Chore Race:

1. Create the household's persons under **Settings → People** in Home
   Assistant, if desired.
2. Create areas under **Settings → Areas, labels & zones**.
3. Optionally create floors and assign the appropriate areas to them.
4. Open the Chore Race planner card.

Chore Race references Home Assistant's person, area, and floor registries; it
does not create separate rooms or floors.

## 3. Participants

In **Teilnehmer**:

1. Select a **Home-Assistant-Person**, or leave the selection empty and enter a
   name manually.
2. Choose **Kind** or **Erwachsen**.
3. Enable **Eingeschränkte Aufgaben erlaubt** only if this participant may
   complete chore types marked for adults.
4. Select **Teilnehmer anlegen**.

The race card shows active participants. Removing a participant from a race
also deactivates them in the planner, reopens their affected tasks from that
race, and retains historical records. Selecting the same Home Assistant person
again in the planner reactivates that participant instead of creating a
duplicate.

## 4. Chore types

A chore type is a reusable template, such as “Mop floor” or “Empty
dishwasher”.

1. Enter its name and default race points.
2. Optionally select a difficulty.
3. Open **Aufgabenbild** and choose one of the bundled illustrations.
4. Under **Rennwertung festlegen**, optionally configure the streak bonus,
   copilot points, and adult-only restriction.
5. Select **Aufgabentyp anlegen**.

Existing templates appear under **Aufgabentypen**. Editing a template changes
future defaults; already created tasks keep their point snapshot. A chore type
that is referenced by a task or recurrence rule cannot be permanently deleted.
Deactivate it instead.

## 5. One-time and recurring tasks

Under **Aufgabe einplanen**:

1. Choose a chore type.
2. Choose a date. For a recurrence this is its start date.
3. Choose no location, a Home Assistant area, or a floor.
4. Optionally choose a preferred participant.
5. Choose a schedule:

   - **Einmalig** — one task on the selected date;
   - **Alle N Tage** — calendar interval in days;
   - **Bestimmte Wochentage** — selected weekdays;
   - **Nach letzter Erledigung** — interval starts after completion;
   - **Einmal pro Monat** — monthly from the start date;
   - **Einmal pro Jahr** — yearly from the start date.

6. Select **Aufgabe einplanen**.

A preferred participant is informational: another eligible active participant
may still complete the task. Area and floor cannot be selected together.

For floor-wide tasks, the card displays the calculated total. Chore Race
multiplies the chore type's base race points by the number of Home Assistant
areas assigned to that floor. A floor without assigned areas cannot be used for
this calculation.

Generated recurrence instances remain when a recurrence rule is paused,
changed, or deleted. Manage schedules under **Wiederholungsregeln**.

## 6. Task chains

**Aufgabenketten** arrange multiple chores in a fixed, cycle-free order. Enter
a name and start date, add the steps, and create the chain. A step is unlocked
only after its predecessor has been completed.

Chain tasks keep stricter history protection than standalone tasks. This
prevents editing a completed sequence into an inconsistent state.

## 7. Daily completion without a race

The race card also serves as the daily task view. Today's and overdue open
tasks remain available; a task does not become impossible merely because its
planned date has passed.

1. Select an open task.
2. Choose the participant who completed it.
3. Confirm the completion.

Without a running race, Chore Race awards the configured normal completion
score. Copilot and fair-play bonuses are available only while a race is
running.

## 8. Running a race

An administrator selects **Rennen starten** on the race card. The current
active participants form the roster and the configured countdown starts.

To complete a task during the race:

1. Select the task.
2. Select the driver.
3. Optionally select a different copilot, or choose the fair-play bonus.
4. Confirm the completion.

Copilot and fair play are mutually exclusive. The race card updates lanes,
points, progress, and the next open task from local Home Assistant events.
An administrator can end a running race early with **Rennen beenden**.

If there is a unique winner and rewards are configured, the winner may choose
one reward.

## 9. Editing, deleting, and undo

The planner lists current templates, recurrence rules, and open tasks with
their available actions.

- An open standalone task without an active completion may be edited or
  deleted, including while a race is running.
- A completed task or a task with an active completion is intentionally
  protected.
- Undoing a completion reopens its task and marks the completion inactive; it
  does not erase history.
- The reopened standalone task can then be edited or deleted.
- Tasks in a chain retain stricter protection once the chain has history.
- Deleting a recurrence rule does not delete tasks it already generated.

These safeguards avoid changing point history retroactively.

## 10. Race reset and participant removal

**Rennen zurücksetzen** reverts that race's active scores, reopens its tasks,
restores the active roster, and returns the session to its ready state.
Historical records remain stored.

The remove icon beside a participant removes that person from the selected
race and deactivates them globally. Completions from that race involving the
person are reverted and affected tasks reopen. Read the confirmation dialog
carefully before proceeding.

## 11. Troubleshooting

### `Unknown command` or `Service ... not found`

The integration and frontend are on different versions. Restart Home
Assistant, update the two card files, increase both resource `?v=` values, and
reload the browser without cache.

### Old card layout remains visible

Verify the JavaScript resources under **Settings → Dashboards → Resources**,
increase their version query, and perform a hard refresh.

### A task cannot be edited or deleted

Check whether it has an active completion or belongs to a task chain with
history. Undo a standalone task's completion before editing it.

### A person, area, or floor is missing

Create or correct it in Home Assistant's corresponding registry, then use the
planner's refresh button. Assign at least one area to a floor before using
floor-wide point multiplication.

For storage recovery and diagnostic details, read
[Troubleshooting](troubleshooting.md). Include Home Assistant and Chore Race
versions plus relevant `chore_race` log lines when
[opening an issue](https://github.com/StomanAUT/chore-race/issues).
