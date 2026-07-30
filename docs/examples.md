# Configuration examples

## Race card

```yaml
type: custom:chore-race-card
title: Familien Grand Prix
target_points: 12
refresh_interval: 30
max_width: 820
accent_color: "#74829a"
```

## Planner card

```yaml
type: custom:chore-race-planner-card
title: Chore Race Planer
max_width: 960
accent_color: "#74829a"
```

The planner reads Home Assistant persons, areas and floors. Participants,
chore types, recurring schedules, task chains and rewards can be managed
without duplicating those registries.

## Create an automatic task

This automation creates one task for a washing-machine completion. Replaying
the same state change does not create a duplicate.

```yaml
automation:
  - alias: "Chore Race: Waschmaschine fertig"
    triggers:
      - trigger: state
        entity_id: sensor.washing_machine_state
        to: "finished"
    actions:
      - action: chore_race.ensure_task
        data:
          chore_type_id: "stable-chore-type-id"
          source: entity
          source_entity_id: "{{ trigger.entity_id }}"
          area_id: "utility_room"
          deduplication_key: >-
            {{ trigger.entity_id }}:{{ trigger.to_state.last_changed.isoformat() }}
```

Use `floor_id` instead of `area_id` for a floor-wide task. The two fields are
mutually exclusive.

## Complete a task outside a race

```yaml
action: chore_race.complete_task
data:
  task_id: "stable-task-id"
  participant_id: "stable-participant-id"
```

Outside a race the configured normal-completion score is awarded. During a
race the race card supplies the driver, optional copilot and fair-play choice.
