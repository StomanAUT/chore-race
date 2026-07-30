"""Business manager for Chore Race."""

from __future__ import annotations

import asyncio
import calendar
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from homeassistant.util import dt as dt_util

from .const import (
    EVENT_DATA_UPDATED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_CREATED,
    EVENT_TASK_REOPENED,
)
from .errors import ConflictError, NotFoundError, ValidationError
from .models import (
    ChoreRaceData,
    ChoreTask,
    ChoreType,
    Completion,
    Difficulty,
    Participant,
    RaceStatus,
    Reward,
    RewardSelection,
    ScoringMode,
    Settings,
    TaskSource,
    TaskStatus,
)
from .scoring import calculate_completion_score
from .storage import ChoreRaceStore

RECURRENCE_FREQUENCIES = {
    "days",
    "weekdays",
    "monthly",
    "yearly",
    "completion_interval",
}


class ChoreRaceManager:
    """Own validation, mutations, aggregation and persistence."""

    def __init__(self, hass: HomeAssistant, store: ChoreRaceStore) -> None:
        """Initialize the manager."""
        self.hass = hass
        self._store = store
        self._data = ChoreRaceData()
        self._mutation_lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()

    @property
    def data(self) -> ChoreRaceData:
        """Expose read-only-by-convention state to HA adapters."""
        return self._data

    async def async_load(self) -> None:
        """Load persisted state."""
        self._data = await self._store.async_load()

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe an entity to manager changes."""
        self._listeners.add(listener)

        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    async def _async_commit(self) -> None:
        await self._store.async_save(self._data)
        for listener in tuple(self._listeners):
            listener()
        self.hass.bus.async_fire(EVENT_DATA_UPDATED)

    @staticmethod
    def _new_id() -> str:
        return uuid4().hex

    @staticmethod
    def _validate_name(name: str) -> str:
        clean = name.strip()
        if not clean:
            raise ValidationError("Name must not be empty")
        if len(clean) > 100:
            raise ValidationError("Name must be at most 100 characters")
        return clean

    @staticmethod
    def _validate_points(points: int, field: str = "points") -> int:
        if isinstance(points, bool) or not 0 <= points <= 1000:
            raise ValidationError(f"{field} must be between 0 and 1000")
        return points

    @staticmethod
    def _validate_location(area_id: str | None, floor_id: str | None) -> None:
        if area_id is not None and floor_id is not None:
            raise ValidationError("A task can use either an area or a floor, not both")

    def _floor_area_count(self, floor_id: str) -> int:
        """Return how many Home Assistant areas belong to one floor."""
        count = sum(
            1
            for area in ar.async_get(self.hass).async_list_areas()
            if getattr(area, "floor_id", None) == floor_id
        )
        if count == 0:
            raise ValidationError("Home Assistant floor has no assigned areas")
        return count

    def _task_points(
        self, base_points: int, floor_id: str | None
    ) -> tuple[int, int]:
        """Return total points and the snapshotted location multiplier."""
        base = self._validate_points(base_points, "base_race_points")
        multiplier = self._floor_area_count(floor_id) if floor_id else 1
        total = self._validate_points(base * multiplier, "race_points")
        return total, multiplier

    async def async_create_participant(
        self,
        name: str,
        *,
        person_entity_id: str | None = None,
        avatar: str | None = None,
        sort_order: int = 0,
        role: str = "child",
        can_do_restricted_tasks: bool = False,
    ) -> Participant:
        """Create an independently identified participant."""
        if role not in {"child", "adult"}:
            raise ValidationError("role must be child or adult")
        participant = Participant(
            id=self._new_id(),
            name=self._validate_name(name),
            person_entity_id=person_entity_id,
            avatar=avatar,
            sort_order=sort_order,
            role=role,
            can_do_restricted_tasks=can_do_restricted_tasks,
        )
        async with self._mutation_lock:
            self._data.participants[participant.id] = participant
            await self._async_commit()
        return participant

    async def async_update_participant(
        self, participant_id: str, **changes: Any
    ) -> Participant:
        """Update a participant without changing its ID."""
        allowed = {
            "name",
            "active",
            "person_entity_id",
            "avatar",
            "sort_order",
            "role",
            "can_do_restricted_tasks",
        }
        if unknown := set(changes) - allowed:
            raise ValidationError(f"Unknown participant fields: {sorted(unknown)}")
        async with self._mutation_lock:
            participant = self._data.participants.get(participant_id)
            if participant is None:
                raise NotFoundError("Participant not found")
            if "name" in changes:
                changes["name"] = self._validate_name(changes["name"])
            if "role" in changes and changes["role"] not in {"child", "adult"}:
                raise ValidationError("role must be child or adult")
            for key, value in changes.items():
                setattr(participant, key, value)
            await self._async_commit()
            return participant

    async def async_create_chore_type(
        self,
        name: str,
        default_race_points: int,
        **values: Any,
    ) -> ChoreType:
        """Create a reusable chore definition."""
        if values.get("difficulty") is not None:
            values["difficulty"] = Difficulty(values["difficulty"])
        chore_type = ChoreType(
            id=self._new_id(),
            name=self._validate_name(name),
            default_race_points=self._validate_points(default_race_points),
            **values,
        )
        async with self._mutation_lock:
            self._data.chore_types[chore_type.id] = chore_type
            await self._async_commit()
        return chore_type

    async def async_update_chore_type(
        self, chore_type_id: str, **changes: Any
    ) -> ChoreType:
        """Update a chore definition; existing task snapshots stay unchanged."""
        allowed = {
            "name",
            "default_race_points",
            "icon",
            "image",
            "streak_enabled",
            "streak_max_bonus",
            "default_copilot_points",
            "active",
            "difficulty",
            "adult_only",
            "confirmation_required",
        }
        if unknown := set(changes) - allowed:
            raise ValidationError(f"Unknown chore type fields: {sorted(unknown)}")
        async with self._mutation_lock:
            chore_type = self._data.chore_types.get(chore_type_id)
            if chore_type is None:
                raise NotFoundError("Chore type not found")
            if "name" in changes:
                changes["name"] = self._validate_name(changes["name"])
            for field in (
                "default_race_points",
                "streak_max_bonus",
                "default_copilot_points",
            ):
                if field in changes:
                    changes[field] = self._validate_points(changes[field], field)
            if changes.get("difficulty") is not None:
                changes["difficulty"] = Difficulty(changes["difficulty"])
            for key, value in changes.items():
                setattr(chore_type, key, value)
            await self._async_commit()
            return chore_type

    async def async_delete_chore_type(self, chore_type_id: str) -> None:
        """Delete an unused chore definition without orphaning planner data."""
        async with self._mutation_lock:
            if chore_type_id not in self._data.chore_types:
                raise NotFoundError("Chore type not found")
            if any(
                task.chore_type_id == chore_type_id
                for task in self._data.tasks.values()
            ):
                raise ConflictError(
                    "Chore types referenced by tasks must be deactivated"
                )
            if any(
                rule["chore_type_id"] == chore_type_id
                for rule in self._data.recurrence_rules.values()
            ):
                raise ConflictError(
                    "Chore types referenced by recurrence rules must be deactivated"
                )
            del self._data.chore_types[chore_type_id]
            await self._async_commit()

    async def async_update_settings(self, **changes: Any) -> Settings:
        """Update persisted planner and future race settings."""
        allowed = {
            "normal_completion_points",
            "fair_play_bonus",
            "race_enabled",
            "race_duration_seconds",
            "race_weekdays",
            "race_ready_time",
        }
        if unknown := set(changes) - allowed:
            raise ValidationError(f"Unknown settings fields: {sorted(unknown)}")

        if "normal_completion_points" in changes:
            changes["normal_completion_points"] = self._validate_points(
                changes["normal_completion_points"],
                "normal_completion_points",
            )
        if "fair_play_bonus" in changes:
            changes["fair_play_bonus"] = self._validate_points(
                changes["fair_play_bonus"],
                "fair_play_bonus",
            )
        if "race_duration_seconds" in changes:
            duration = changes["race_duration_seconds"]
            if isinstance(duration, bool) or not 60 <= duration <= 14400:
                raise ValidationError(
                    "race_duration_seconds must be between 60 and 14400"
                )
        if "race_weekdays" in changes:
            weekdays = changes["race_weekdays"]
            if (
                not isinstance(weekdays, list)
                or not weekdays
                or any(
                    isinstance(day, bool)
                    or not isinstance(day, int)
                    or day not in range(7)
                    for day in weekdays
                )
            ):
                raise ValidationError(
                    "race_weekdays must contain weekdays 0 through 6"
                )
            changes["race_weekdays"] = sorted(set(weekdays))
        if "race_ready_time" in changes:
            ready_time = changes["race_ready_time"]
            try:
                hour_text, minute_text = ready_time.split(":", maxsplit=1)
                hour = int(hour_text)
                minute = int(minute_text)
            except (AttributeError, TypeError, ValueError) as err:
                raise ValidationError("race_ready_time must use HH:MM") from err
            if (
                len(ready_time) != 5
                or not 0 <= hour <= 23
                or not 0 <= minute <= 59
            ):
                raise ValidationError("race_ready_time must use HH:MM")

        async with self._mutation_lock:
            for key, value in changes.items():
                setattr(self._data.settings, key, value)
            await self._async_commit()
            return self._data.settings

    async def async_create_reward(
        self,
        name: str,
        *,
        icon: str = "mdi:gift-outline",
        image: str | None = None,
        sort_order: int = 0,
    ) -> Reward:
        """Create a reward that a race champion may choose."""
        reward = Reward(
            id=self._new_id(),
            name=self._validate_name(name),
            icon=icon.strip() or "mdi:gift-outline",
            image=image,
            sort_order=sort_order,
        )
        async with self._mutation_lock:
            self._data.rewards[reward.id] = reward
            await self._async_commit()
        return reward

    async def async_update_reward(
        self, reward_id: str, **changes: Any
    ) -> Reward:
        """Update a reward while preserving historical selections."""
        allowed = {"name", "icon", "image", "active", "sort_order"}
        if unknown := set(changes) - allowed:
            raise ValidationError(f"Unknown reward fields: {sorted(unknown)}")
        async with self._mutation_lock:
            reward = self._data.rewards.get(reward_id)
            if reward is None:
                raise NotFoundError("Reward not found")
            if "name" in changes:
                changes["name"] = self._validate_name(changes["name"])
            if "icon" in changes:
                changes["icon"] = (
                    changes["icon"].strip() or "mdi:gift-outline"
                )
            for key, value in changes.items():
                setattr(reward, key, value)
            await self._async_commit()
            return reward

    async def async_delete_reward(self, reward_id: str) -> None:
        """Delete only an unused reward; selected rewards remain auditable."""
        async with self._mutation_lock:
            if reward_id not in self._data.rewards:
                raise NotFoundError("Reward not found")
            if any(
                selection.reward_id == reward_id
                for selection in self._data.reward_selections.values()
            ):
                raise ConflictError(
                    "Rewards referenced by winner selections must be deactivated"
                )
            del self._data.rewards[reward_id]
            await self._async_commit()

    async def async_select_reward(
        self, race_id: str, reward_id: str
    ) -> dict[str, Any]:
        """Persist the unique champion's one immutable reward choice."""
        async with self._mutation_lock:
            race = self._require_race(race_id)
            state = self.race_state(race["id"])
            if state["status"] != RaceStatus.FINISHED:
                raise ConflictError("Rewards can only be selected after a race")
            champion = state["champion"]
            if champion is None:
                raise ConflictError(
                    "A reward requires one unique champion with positive points"
                )
            reward = self._data.rewards.get(reward_id)
            if reward is None or not reward.active:
                raise NotFoundError("Active reward not found")
            if any(
                selection.race_id == race["id"]
                for selection in self._data.reward_selections.values()
            ):
                raise ConflictError("A reward was already selected for this race")
            selection = RewardSelection(
                id=self._new_id(),
                race_id=race["id"],
                reward_id=reward.id,
                participant_id=champion["participant_id"],
                selected_at=dt_util.utcnow(),
            )
            self._data.reward_selections[selection.id] = selection
            await self._async_commit()
            return self._reward_selection_snapshot(selection)

    async def async_create_task(
        self,
        chore_type_id: str,
        task_date: date,
        *,
        area_id: str | None = None,
        floor_id: str | None = None,
        race_points: int | None = None,
        preferred_participant_id: str | None = None,
        source: TaskSource | str = TaskSource.MANUAL,
        source_entity_id: str | None = None,
        deduplication_key: str | None = None,
        chain_id: str | None = None,
        chain_step_id: str | None = None,
        blocked: bool = False,
    ) -> ChoreTask:
        """Create a concrete task with point values snapshotted now."""
        async with self._mutation_lock:
            task = self._build_task(
                chore_type_id,
                task_date,
                area_id=area_id,
                floor_id=floor_id,
                race_points=race_points,
                preferred_participant_id=preferred_participant_id,
                source=source,
                source_entity_id=source_entity_id,
                deduplication_key=deduplication_key,
                chain_id=chain_id,
                chain_step_id=chain_step_id,
                blocked=blocked,
            )
            self._data.tasks[task.id] = task
            await self._async_commit()
        self._fire_task_created(task)
        return task

    def _build_task(
        self,
        chore_type_id: str,
        task_date: date,
        *,
        area_id: str | None,
        floor_id: str | None,
        race_points: int | None,
        preferred_participant_id: str | None,
        source: TaskSource | str,
        source_entity_id: str | None,
        deduplication_key: str | None,
        chain_id: str | None,
        chain_step_id: str | None,
        blocked: bool,
    ) -> ChoreTask:
        """Validate and build one task while the caller owns the mutation lock."""
        chore_type = self._data.chore_types.get(chore_type_id)
        if chore_type is None:
            raise NotFoundError("Chore type not found")
        if preferred_participant_id is not None:
            self._require_participant(preferred_participant_id)
        self._validate_location(area_id, floor_id)
        if (
            area_id is not None
            and ar.async_get(self.hass).async_get_area(area_id) is None
        ):
            raise ValidationError("Home Assistant area does not exist")
        if (
            floor_id is not None
            and fr.async_get(self.hass).async_get_floor(floor_id) is None
        ):
            raise ValidationError("Home Assistant floor does not exist")
        try:
            task_source = TaskSource(source)
        except ValueError as err:
            raise ValidationError("Unsupported task source") from err
        if task_source is TaskSource.ENTITY and not source_entity_id:
            raise ValidationError("Entity tasks require source_entity_id")
        clean_key = deduplication_key.strip() if deduplication_key else None
        if clean_key is not None and len(clean_key) > 255:
            raise ValidationError("deduplication_key must be at most 255 characters")
        base_points = (
            chore_type.default_race_points if race_points is None else race_points
        )
        total_points, points_multiplier = self._task_points(
            base_points, floor_id
        )
        now = dt_util.utcnow()
        return ChoreTask(
            id=self._new_id(),
            chore_type_id=chore_type_id,
            area_id=area_id,
            floor_id=floor_id,
            date=task_date,
            race_points=total_points,
            preferred_participant_id=preferred_participant_id,
            source=task_source,
            source_entity_id=source_entity_id,
            deduplication_key=clean_key,
            chain_id=chain_id,
            chain_step_id=chain_step_id,
            blocked=blocked,
            base_race_points=base_points,
            points_multiplier=points_multiplier,
            created_at=now,
            updated_at=now,
        )

    def _fire_task_created(self, task: ChoreTask) -> None:
        self.hass.bus.async_fire(
            EVENT_TASK_CREATED,
            {
                "task_id": task.id,
                "source": task.source.value,
                "source_entity_id": task.source_entity_id,
            },
        )

    async def async_ensure_task(
        self,
        chore_type_id: str,
        task_date: date,
        *,
        source: TaskSource | str,
        source_entity_id: str,
        deduplication_key: str | None = None,
        area_id: str | None = None,
        floor_id: str | None = None,
        race_points: int | None = None,
        preferred_participant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an automation task once and return repeat calls idempotently."""
        try:
            task_source = TaskSource(source)
        except ValueError as err:
            raise ValidationError("Unsupported task source") from err
        if task_source not in {TaskSource.ENTITY, TaskSource.AUTOMATION}:
            raise ValidationError("ensure_task source must be entity or automation")
        if not source_entity_id:
            raise ValidationError("source_entity_id is required")
        clean_key = deduplication_key.strip() if deduplication_key else None
        if clean_key is None:
            location = area_id or floor_id or "none"
            clean_key = (
                f"{task_source.value}:{source_entity_id}:{chore_type_id}:"
                f"{task_date.isoformat()}:{location}"
            )
        async with self._mutation_lock:
            existing = next(
                (
                    task
                    for task in self._data.tasks.values()
                    if task.deduplication_key == clean_key
                ),
                None,
            )
            if existing is not None:
                return {"created": False, "task": existing.to_dict()}
            task = self._build_task(
                chore_type_id,
                task_date,
                area_id=area_id,
                floor_id=floor_id,
                race_points=race_points,
                preferred_participant_id=preferred_participant_id,
                source=task_source,
                source_entity_id=source_entity_id,
                deduplication_key=clean_key,
                chain_id=None,
                chain_step_id=None,
                blocked=False,
            )
            self._data.tasks[task.id] = task
            await self._async_commit()
        self._fire_task_created(task)
        return {"created": True, "task": task.to_dict()}

    async def async_create_recurrence_rule(
        self,
        chore_type_id: str,
        start_date: date,
        *,
        frequency: str,
        interval: int = 1,
        weekdays: list[int] | None = None,
        area_id: str | None = None,
        floor_id: str | None = None,
        preferred_participant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a recurrence rule and materialize its first due task."""
        if frequency not in RECURRENCE_FREQUENCIES:
            raise ValidationError("Unsupported recurrence frequency")
        if isinstance(interval, bool) or not 1 <= interval <= 365:
            raise ValidationError("interval must be between 1 and 365")
        normalized_weekdays = self._validate_recurrence_weekdays(
            weekdays, required=frequency == "weekdays"
        )
        if chore_type_id not in self._data.chore_types:
            raise NotFoundError("Chore type not found")
        if preferred_participant_id is not None:
            self._require_participant(preferred_participant_id)
        self._validate_location(area_id, floor_id)
        if (
            area_id is not None
            and ar.async_get(self.hass).async_get_area(area_id) is None
        ):
            raise ValidationError("Home Assistant area does not exist")
        if (
            floor_id is not None
            and fr.async_get(self.hass).async_get_floor(floor_id) is None
        ):
            raise ValidationError("Home Assistant floor does not exist")
        rule = {
            "id": self._new_id(),
            "chore_type_id": chore_type_id,
            "start_date": start_date.isoformat(),
            "frequency": frequency,
            "interval": interval,
            "weekdays": normalized_weekdays,
            "area_id": area_id,
            "floor_id": floor_id,
            "preferred_participant_id": preferred_participant_id,
            "active": True,
        }
        async with self._mutation_lock:
            self._data.recurrence_rules[rule["id"]] = rule
            await self._async_commit()
        await self.async_materialize_recurrences(self.today())
        return rule

    async def async_update_recurrence_rule(
        self, rule_id: str, **changes: Any
    ) -> dict[str, Any]:
        """Update future recurrence behavior without rewriting existing tasks."""
        allowed = {
            "chore_type_id",
            "start_date",
            "frequency",
            "interval",
            "weekdays",
            "area_id",
            "floor_id",
            "preferred_participant_id",
            "active",
        }
        if unknown := set(changes) - allowed:
            raise ValidationError(f"Unknown recurrence fields: {sorted(unknown)}")
        async with self._mutation_lock:
            rule = self._data.recurrence_rules.get(rule_id)
            if rule is None:
                raise NotFoundError("Recurrence rule not found")
            if "chore_type_id" in changes:
                if changes["chore_type_id"] not in self._data.chore_types:
                    raise NotFoundError("Chore type not found")
            if "start_date" in changes:
                start_date = changes["start_date"]
                if not isinstance(start_date, date):
                    raise ValidationError("start_date must be a date")
                changes["start_date"] = start_date.isoformat()
            if (
                "frequency" in changes
                and changes["frequency"] not in RECURRENCE_FREQUENCIES
            ):
                raise ValidationError("Unsupported recurrence frequency")
            if "interval" in changes:
                interval = changes["interval"]
                if isinstance(interval, bool) or not 1 <= interval <= 365:
                    raise ValidationError("interval must be between 1 and 365")
            final_frequency = changes.get("frequency", rule["frequency"])
            if "weekdays" in changes or final_frequency == "weekdays":
                changes["weekdays"] = self._validate_recurrence_weekdays(
                    changes.get("weekdays", rule.get("weekdays")),
                    required=final_frequency == "weekdays",
                )
            if changes.get("preferred_participant_id") is not None:
                self._require_participant(changes["preferred_participant_id"])
            if (
                changes.get("area_id") is not None
                and ar.async_get(self.hass).async_get_area(changes["area_id"]) is None
            ):
                raise ValidationError("Home Assistant area does not exist")
            if (
                changes.get("floor_id") is not None
                and fr.async_get(self.hass).async_get_floor(changes["floor_id"]) is None
            ):
                raise ValidationError("Home Assistant floor does not exist")
            final_area_id = changes.get("area_id", rule.get("area_id"))
            final_floor_id = changes.get("floor_id", rule.get("floor_id"))
            self._validate_location(final_area_id, final_floor_id)
            rule.update(changes)
            await self._async_commit()
            return rule

    async def async_delete_recurrence_rule(self, rule_id: str) -> None:
        """Delete a recurrence rule while preserving materialized tasks."""
        async with self._mutation_lock:
            if rule_id not in self._data.recurrence_rules:
                raise NotFoundError("Recurrence rule not found")
            del self._data.recurrence_rules[rule_id]
            await self._async_commit()

    @staticmethod
    def _validate_recurrence_weekdays(
        weekdays: list[int] | None, *, required: bool
    ) -> list[int]:
        values = weekdays or []
        if any(
            isinstance(day, bool)
            or not isinstance(day, int)
            or day not in range(7)
            for day in values
        ):
            raise ValidationError("weekdays must contain values 0 through 6")
        normalized = sorted(set(values))
        if required and not normalized:
            raise ValidationError("At least one weekday must be selected")
        return normalized

    def _rule_is_due(self, rule: dict[str, Any], day: date) -> bool:
        start = date.fromisoformat(rule["start_date"])
        if day < start:
            return False
        frequency = rule["frequency"]
        if frequency == "days":
            return (day - start).days % int(rule.get("interval", 1)) == 0
        if frequency == "weekdays":
            return day.weekday() in rule.get("weekdays", [])
        if frequency == "completion_interval":
            source_id = f"recurrence:{rule['id']}"
            generated_tasks = [
                task
                for task in self._data.tasks.values()
                if task.source_entity_id == source_id
            ]
            if any(task.status == TaskStatus.OPEN for task in generated_tasks):
                return False
            task_ids = {task.id for task in generated_tasks}
            last_completion = max(
                (
                    completion.completed_at
                    for completion in self._data.completions.values()
                    if completion.active and completion.task_id in task_ids
                ),
                default=None,
            )
            if last_completion is None:
                return not generated_tasks
            last_day = dt_util.as_local(last_completion).date()
            return day >= last_day + timedelta(
                days=int(rule.get("interval", 1))
            )
        if frequency == "monthly":
            last_day = calendar.monthrange(day.year, day.month)[1]
            return day.day == min(start.day, last_day)
        if frequency == "yearly" and day.month == start.month:
            last_day = calendar.monthrange(day.year, day.month)[1]
            return day.day == min(start.day, last_day)
        return False

    async def async_materialize_recurrences(self, day: date | None = None) -> int:
        """Create each due recurring task at most once for a date."""
        current = day or self.today()
        due_rules = [
            rule
            for rule in self._data.recurrence_rules.values()
            if rule.get("active", True) and self._rule_is_due(rule, current)
        ]
        created = 0
        for rule in due_rules:
            source_id = f"recurrence:{rule['id']}"
            if any(
                task.date == current and task.source_entity_id == source_id
                for task in self._data.tasks.values()
            ):
                continue
            await self.async_create_task(
                rule["chore_type_id"],
                current,
                area_id=rule.get("area_id"),
                floor_id=rule.get("floor_id"),
                preferred_participant_id=rule.get("preferred_participant_id"),
                source=TaskSource.RECURRING,
                source_entity_id=source_id,
            )
            created += 1
        return created

    async def async_update_task(
        self, task_id: str, **changes: Any
    ) -> ChoreTask:
        """Update an untouched open task while preserving historical records."""
        allowed = {
            "chore_type_id",
            "date",
            "area_id",
            "floor_id",
            "race_points",
            "preferred_participant_id",
            "blocked",
        }
        if unknown := set(changes) - allowed:
            raise ValidationError(f"Unknown task fields: {sorted(unknown)}")
        async with self._mutation_lock:
            task = self._require_task(task_id)
            self._ensure_task_mutable(task)
            if (
                "chore_type_id" in changes
                and changes["chore_type_id"] not in self._data.chore_types
            ):
                raise NotFoundError("Chore type not found")
            if "date" in changes and not isinstance(changes["date"], date):
                raise ValidationError("date must be a date")
            if changes.get("area_id") is not None:
                registry = ar.async_get(self.hass)
                if registry.async_get_area(changes["area_id"]) is None:
                    raise ValidationError("Home Assistant area does not exist")
            if changes.get("floor_id") is not None:
                registry = fr.async_get(self.hass)
                if registry.async_get_floor(changes["floor_id"]) is None:
                    raise ValidationError("Home Assistant floor does not exist")
            final_area_id = changes.get("area_id", task.area_id)
            final_floor_id = changes.get("floor_id", task.floor_id)
            self._validate_location(final_area_id, final_floor_id)
            if changes.get("preferred_participant_id") is not None:
                self._require_participant(changes["preferred_participant_id"])
            if {"race_points", "area_id", "floor_id"} & changes.keys():
                base_points = changes.get(
                    "race_points",
                    task.base_race_points
                    if task.base_race_points is not None
                    else task.race_points,
                )
                total_points, points_multiplier = self._task_points(
                    base_points, final_floor_id
                )
                changes["race_points"] = total_points
                changes["base_race_points"] = base_points
                changes["points_multiplier"] = points_multiplier
            if "blocked" in changes and not isinstance(changes["blocked"], bool):
                raise ValidationError("blocked must be a boolean")
            for key, value in changes.items():
                setattr(task, key, value)
            task.updated_at = dt_util.utcnow()
            await self._async_commit()
            return task

    async def async_delete_task(self, task_id: str) -> None:
        """Delete an untouched open task."""
        async with self._mutation_lock:
            task = self._require_task(task_id)
            self._ensure_task_mutable(task)
            del self._data.tasks[task.id]
            await self._async_commit()

    async def async_complete_task(
        self,
        task_id: str,
        participant_id: str,
        *,
        require_active_race: bool = False,
        copilot_participant_id: str | None = None,
        fair_play: bool = False,
    ) -> Completion:
        """Atomically complete a task once and award normal or race points."""
        async with self._mutation_lock:
            task = self._require_task(task_id)
            participant = self._require_participant(participant_id)
            chore_type = self._data.chore_types[task.chore_type_id]
            if not isinstance(fair_play, bool):
                raise ValidationError("fair_play must be a boolean")
            if not participant.active:
                raise ValidationError("Participant is inactive")
            if (
                chore_type.adult_only
                and participant.role != "adult"
                and not participant.can_do_restricted_tasks
            ):
                raise ValidationError("Participant may not complete adult-only tasks")
            if task.blocked:
                raise ConflictError("Task is blocked")
            if task.status is not TaskStatus.OPEN:
                raise ConflictError("Task is not open")
            if self._active_completion_for_task(task_id) is not None:
                raise ConflictError("Task already has an active completion")
            now = dt_util.utcnow()
            race = self._active_race(now)
            if require_active_race and race is None:
                raise ConflictError("No race is running")
            if race is None and (copilot_participant_id or fair_play):
                raise ConflictError(
                    "Copilot and fair-play bonuses require a running race"
                )
            if (
                race is not None
                and participant.id not in self._race_participant_ids(race)
            ):
                raise ValidationError("Participant is not in this race")
            if copilot_participant_id and fair_play:
                raise ValidationError(
                    "Copilot and fair-play bonuses cannot be combined"
                )
            copilot = None
            if copilot_participant_id is not None:
                copilot = self._require_participant(copilot_participant_id)
                if copilot.id == participant.id:
                    raise ValidationError("Driver and copilot must be different")
                if not copilot.active:
                    raise ValidationError("Copilot is inactive")
                if (
                    race is not None
                    and copilot.id not in self._race_participant_ids(race)
                ):
                    raise ValidationError("Copilot is not in this race")
                if (
                    chore_type.adult_only
                    and copilot.role != "adult"
                    and not copilot.can_do_restricted_tasks
                ):
                    raise ValidationError(
                        "Copilot may not assist with adult-only tasks"
                    )
            race_id = race["id"] if race is not None else None
            streak_length = (
                self._race_driver_completion_count(race_id, participant.id)
                if race_id is not None
                else 0
            )
            score = calculate_completion_score(
                task,
                chore_type,
                self._data.settings,
                race_id=race_id,
                fair_play=fair_play,
                has_copilot=copilot is not None,
                streak_length=streak_length,
            )
            completion = Completion(
                id=self._new_id(),
                task_id=task.id,
                participant_id=participant.id,
                completed_at=now,
                base_points_awarded=score.base,
                fair_play_bonus=score.fair_play,
                streak_bonus=score.streak,
                copilot_participant_id=copilot.id if copilot else None,
                copilot_points_awarded=score.copilot,
                total_points_awarded=score.total,
                scoring_mode=score.mode,
                race_id=race_id,
            )
            task.status = TaskStatus.COMPLETED
            task.updated_at = now
            self._data.completions[completion.id] = completion
            await self._async_commit()
            self.hass.bus.async_fire(
                EVENT_TASK_COMPLETED,
                {
                    "task_id": task.id,
                    "participant_id": participant.id,
                    "points": completion.total_points_awarded,
                    "base_points": completion.base_points_awarded,
                    "fair_play_bonus": completion.fair_play_bonus,
                    "streak_bonus": completion.streak_bonus,
                    "copilot_participant_id": completion.copilot_participant_id,
                    "copilot_points": completion.copilot_points_awarded,
                    "race_id": completion.race_id,
                },
            )
            return completion

    def _race_driver_completion_count(
        self, race_id: str, participant_id: str
    ) -> int:
        """Count active driver completions already earned in one race."""
        return sum(
            completion.active
            and completion.race_id == race_id
            and completion.participant_id == participant_id
            for completion in self._data.completions.values()
        )

    def _active_race(self, now: datetime | None = None) -> dict[str, Any] | None:
        """Return the running, non-expired race session."""
        current = now or dt_util.utcnow()
        for race in self._data.race_sessions.values():
            if race.get("status") != RaceStatus.RUNNING:
                continue
            if datetime.fromisoformat(race["ends_at"]) > current:
                return race
        return None

    async def async_start_race(self) -> dict[str, Any]:
        """Start one race, closing an expired session if necessary."""
        async with self._mutation_lock:
            if not self._data.settings.race_enabled:
                raise ValidationError("Races are disabled")
            now = dt_util.utcnow()
            for race in self._data.race_sessions.values():
                if race.get("status") != RaceStatus.RUNNING:
                    continue
                if datetime.fromisoformat(race["ends_at"]) > now:
                    raise ConflictError("A race is already running")
                race["status"] = RaceStatus.FINISHED.value
                race["finished_at"] = race["ends_at"]
            race_id = self._new_id()
            race = {
                "id": race_id,
                "status": RaceStatus.RUNNING.value,
                "participant_ids": [
                    participant.id
                    for participant in self._data.participants.values()
                    if participant.active
                ],
                "started_at": now.isoformat(),
                "ends_at": (
                    now
                    + timedelta(
                        seconds=self._data.settings.race_duration_seconds
                    )
                ).isoformat(),
                "finished_at": None,
                "reset_at": None,
            }
            self._data.race_sessions[race_id] = race
            await self._async_commit()
            return self.race_state(race_id)

    async def async_stop_race(self) -> dict[str, Any]:
        """Finish the currently running race."""
        async with self._mutation_lock:
            now = dt_util.utcnow()
            race = self._active_race(now)
            if race is None:
                raise ConflictError("No race is running")
            race["status"] = RaceStatus.FINISHED.value
            race["finished_at"] = now.isoformat()
            await self._async_commit()
            return self.race_state(race["id"], now=now)

    def _race_participant_ids(self, race: dict[str, Any]) -> list[str]:
        """Return the persisted race roster with a legacy fallback."""
        if "participant_ids" not in race:
            race["participant_ids"] = [
                participant.id
                for participant in self._data.participants.values()
                if participant.active
            ]
        return race["participant_ids"]

    def _require_race(self, race_id: str | None = None) -> dict[str, Any]:
        race = self._data.race_sessions.get(race_id) if race_id else None
        if race is None and self._data.race_sessions:
            race = max(
                self._data.race_sessions.values(),
                key=lambda item: item["started_at"],
            )
        if race is None:
            raise NotFoundError("Race not found")
        return race

    def _revert_race_completions(
        self,
        race_id: str,
        now: datetime,
        participant_id: str | None = None,
    ) -> int:
        """Reopen tasks for active completions matching one race and participant."""
        reverted = 0
        for completion in self._data.completions.values():
            if not completion.active or completion.race_id != race_id:
                continue
            if participant_id is not None and participant_id not in {
                completion.participant_id,
                completion.copilot_participant_id,
            }:
                continue
            completion.reverted_at = now
            if task := self._data.tasks.get(completion.task_id):
                task.status = TaskStatus.OPEN
                task.updated_at = now
            reverted += 1
        return reverted

    async def async_reset_race(
        self, race_id: str | None = None
    ) -> dict[str, Any]:
        """Reset only one race, reopening its tasks and restoring its roster."""
        async with self._mutation_lock:
            race = self._require_race(race_id)
            now = dt_util.utcnow()
            reverted = self._revert_race_completions(race["id"], now)
            race.update(
                {
                    "status": RaceStatus.READY.value,
                    "participant_ids": [
                        participant.id
                        for participant in self._data.participants.values()
                        if participant.active
                    ],
                    "finished_at": None,
                    "reset_at": now.isoformat(),
                }
            )
            await self._async_commit()
            state = self.race_state(race["id"], now=now)
            state["reverted_completions"] = reverted
            return state

    async def async_remove_race_participant(
        self,
        participant_id: str,
        race_id: str | None = None,
    ) -> dict[str, Any]:
        """Remove one participant only from a race and rewind affected work."""
        async with self._mutation_lock:
            self._require_participant(participant_id)
            race = self._require_race(race_id)
            participant_ids = self._race_participant_ids(race)
            if participant_id not in participant_ids:
                raise NotFoundError("Participant is not in this race")
            now = dt_util.utcnow()
            participant_ids.remove(participant_id)
            reverted = self._revert_race_completions(
                race["id"], now, participant_id
            )
            await self._async_commit()
            state = self.race_state(race["id"], now=now)
            state["reverted_completions"] = reverted
            return state

    def rewards_snapshot(
        self, *, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        """Return rewards ordered for planner or champion presentation."""
        return [
            reward.to_dict()
            for reward in sorted(
                self._data.rewards.values(),
                key=lambda item: (item.sort_order, item.name.casefold()),
            )
            if include_inactive or reward.active
        ]

    def _reward_selection_snapshot(
        self, selection: RewardSelection
    ) -> dict[str, Any]:
        """Enrich a persisted winner choice with current presentation names."""
        reward = self._data.rewards.get(selection.reward_id)
        participant = self._data.participants.get(selection.participant_id)
        return {
            **selection.to_dict(),
            "reward_name": reward.name if reward else "Belohnung",
            "reward_icon": reward.icon if reward else "mdi:gift-outline",
            "reward_image": reward.image if reward else None,
            "participant_name": (
                participant.name if participant else "Teilnehmer"
            ),
        }

    def _reward_selection_for_race(
        self, race_id: str
    ) -> dict[str, Any] | None:
        selection = next(
            (
                item
                for item in self._data.reward_selections.values()
                if item.race_id == race_id
            ),
            None,
        )
        return (
            self._reward_selection_snapshot(selection)
            if selection is not None
            else None
        )

    def last_reward_selection(self) -> dict[str, Any] | None:
        """Return the household's most recent winner choice."""
        selection = max(
            self._data.reward_selections.values(),
            key=lambda item: item.selected_at,
            default=None,
        )
        return (
            self._reward_selection_snapshot(selection)
            if selection is not None
            else None
        )

    def race_state(
        self, race_id: str | None = None, *, now: datetime | None = None
    ) -> dict[str, Any]:
        """Return countdown and leaderboard for one or the latest race."""
        current = now or dt_util.utcnow()
        race = self._data.race_sessions.get(race_id) if race_id else None
        if race is None and self._data.race_sessions:
            race = max(
                self._data.race_sessions.values(),
                key=lambda item: item["started_at"],
            )
        if race is None:
            open_tasks = self._race_open_tasks()
            return {
                "status": RaceStatus.READY.value,
                "race_id": None,
                "started_at": None,
                "ends_at": None,
                "finished_at": None,
                "reset_at": None,
                "remaining_seconds": 0,
                "leaderboard": [],
                "participant_ids": [
                    participant.id
                    for participant in self._data.participants.values()
                    if participant.active
                ],
                "champion": None,
                "rewards": self.rewards_snapshot(),
                "reward_selection": None,
                "last_reward_selection": self.last_reward_selection(),
                "last_completion": None,
                "current_task": open_tasks[0] if open_tasks else None,
                "open_tasks": open_tasks,
            }
        ends_at = datetime.fromisoformat(race["ends_at"])
        remaining = max(0, int((ends_at - current).total_seconds()))
        status = race["status"]
        if status == RaceStatus.RUNNING and remaining == 0:
            status = RaceStatus.FINISHED.value
        if status != RaceStatus.RUNNING:
            remaining = 0
        leaderboard = self._race_leaderboard(race["id"])
        champion = self._race_champion(leaderboard) if status == "finished" else None
        open_tasks = self._race_open_tasks()
        return {
            "status": status,
            "race_id": race["id"],
            "started_at": race["started_at"],
            "ends_at": race["ends_at"],
            "finished_at": race.get("finished_at"),
            "reset_at": race.get("reset_at"),
            "remaining_seconds": remaining,
            "leaderboard": leaderboard,
            "participant_ids": list(self._race_participant_ids(race)),
            "champion": champion,
            "rewards": self.rewards_snapshot(),
            "reward_selection": self._reward_selection_for_race(race["id"]),
            "last_reward_selection": self.last_reward_selection(),
            "last_completion": self._race_last_completion(race["id"]),
            "current_task": open_tasks[0] if open_tasks else None,
            "open_tasks": open_tasks,
        }

    def _race_leaderboard(self, race_id: str) -> list[dict[str, Any]]:
        """Return exact session totals and an auditable bonus breakdown."""
        race = self._data.race_sessions[race_id]
        participant_ids = set(self._race_participant_ids(race))
        rows: dict[str, dict[str, Any]] = {
            participant.id: {
                "participant_id": participant.id,
                "name": participant.name,
                "points": 0,
                "base_points": 0,
                "fair_play_bonus": 0,
                "streak_bonus": 0,
                "copilot_points": 0,
            }
            for participant in self._data.participants.values()
            if participant.active and participant.id in participant_ids
        }
        for completion in self._data.completions.values():
            if not completion.active or completion.race_id != race_id:
                continue
            driver = self._data.participants.get(completion.participant_id)
            if driver is not None and driver.id in participant_ids:
                row = rows.setdefault(
                    driver.id,
                    {
                        "participant_id": driver.id,
                        "name": driver.name,
                        "points": 0,
                        "base_points": 0,
                        "fair_play_bonus": 0,
                        "streak_bonus": 0,
                        "copilot_points": 0,
                    },
                )
                row["base_points"] += completion.base_points_awarded
                row["fair_play_bonus"] += completion.fair_play_bonus
                row["streak_bonus"] += completion.streak_bonus
                row["points"] += completion.total_points_awarded
            copilot = self._data.participants.get(
                completion.copilot_participant_id or ""
            )
            if copilot is not None and copilot.id in participant_ids:
                row = rows.setdefault(
                    copilot.id,
                    {
                        "participant_id": copilot.id,
                        "name": copilot.name,
                        "points": 0,
                        "base_points": 0,
                        "fair_play_bonus": 0,
                        "streak_bonus": 0,
                        "copilot_points": 0,
                    },
                )
                row["copilot_points"] += completion.copilot_points_awarded
                row["points"] += completion.copilot_points_awarded
        leaderboard = sorted(
            rows.values(),
            key=lambda item: (-item["points"], item["name"].casefold()),
        )
        previous_points: int | None = None
        rank = 0
        for index, row in enumerate(leaderboard, start=1):
            if row["points"] != previous_points:
                rank = index
                previous_points = row["points"]
            row["rank"] = rank
        return leaderboard

    @staticmethod
    def _race_champion(
        leaderboard: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return a unique positive session champion, never a tie."""
        if not leaderboard or leaderboard[0]["points"] <= 0:
            return None
        if (
            len(leaderboard) > 1
            and leaderboard[0]["points"] == leaderboard[1]["points"]
        ):
            return None
        return dict(leaderboard[0])

    def _race_last_completion(self, race_id: str) -> dict[str, Any] | None:
        """Return the most recent active completion with presentation names."""
        completion = max(
            (
                item
                for item in self._data.completions.values()
                if item.active and item.race_id == race_id
            ),
            key=lambda item: item.completed_at,
            default=None,
        )
        if completion is None:
            return None
        task = self._data.tasks.get(completion.task_id)
        chore_type = (
            self._data.chore_types.get(task.chore_type_id)
            if task is not None
            else None
        )
        driver = self._data.participants.get(completion.participant_id)
        copilot = self._data.participants.get(
            completion.copilot_participant_id or ""
        )
        return {
            "completion_id": completion.id,
            "task_id": completion.task_id,
            "task_name": chore_type.name if chore_type else "Aufgabe",
            "participant_id": completion.participant_id,
            "participant_name": driver.name if driver else "Teilnehmer",
            "base_points": completion.base_points_awarded,
            "fair_play_bonus": completion.fair_play_bonus,
            "streak_bonus": completion.streak_bonus,
            "total_points": completion.total_points_awarded,
            "copilot_participant_id": completion.copilot_participant_id,
            "copilot_name": copilot.name if copilot else None,
            "copilot_points": completion.copilot_points_awarded,
            "completed_at": completion.completed_at.isoformat(),
        }

    def _race_open_tasks(self) -> list[dict[str, Any]]:
        """Return today's actionable tasks with stable presentation snapshots."""
        today = self.today()
        tasks = sorted(
            (
                task
                for task in self._data.tasks.values()
                if task.date == today
                and task.status is TaskStatus.OPEN
                and not task.blocked
                and self._data.chore_types.get(task.chore_type_id) is not None
                and self._data.chore_types[task.chore_type_id].active
            ),
            key=lambda task: (task.created_at, task.id),
        )
        return [
            {
                **task.to_dict(),
                "name": self._data.chore_types[task.chore_type_id].name,
                "image": self._data.chore_types[task.chore_type_id].image,
                "icon": self._data.chore_types[task.chore_type_id].icon,
                "adult_only": self._data.chore_types[
                    task.chore_type_id
                ].adult_only,
            }
            for task in tasks
        ]

    async def async_undo_completion(self, completion_id: str) -> Completion:
        """Revert a completion while preserving its audit history."""
        async with self._mutation_lock:
            completion = self._data.completions.get(completion_id)
            if completion is None:
                raise NotFoundError("Completion not found")
            if not completion.active:
                raise ConflictError("Completion is already reverted")
            task = self._require_task(completion.task_id)
            now = dt_util.utcnow()
            completion.reverted_at = now
            task.status = TaskStatus.OPEN
            task.updated_at = now
            await self._async_commit()
            self.hass.bus.async_fire(
                EVENT_TASK_REOPENED,
                {"task_id": task.id, "completion_id": completion.id},
            )
            return completion

    def _require_participant(self, participant_id: str) -> Participant:
        participant = self._data.participants.get(participant_id)
        if participant is None:
            raise NotFoundError("Participant not found")
        return participant

    def _require_task(self, task_id: str) -> ChoreTask:
        task = self._data.tasks.get(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        return task

    def _ensure_task_mutable(self, task: ChoreTask) -> None:
        """Reject edits that could rewrite completion history."""
        if task.status is not TaskStatus.OPEN:
            raise ConflictError("Only open tasks can be changed")
        if any(
            completion.task_id == task.id
            for completion in self._data.completions.values()
        ):
            raise ConflictError("Tasks with completion history cannot be changed")

    def _active_completion_for_task(self, task_id: str) -> Completion | None:
        return next(
            (
                completion
                for completion in self._data.completions.values()
                if completion.task_id == task_id and completion.active
            ),
            None,
        )

    def today(self) -> date:
        """Return today in the configured HA time zone."""
        return dt_util.now().date()

    def _week_bounds(self, day: date | None = None) -> tuple[date, date]:
        current = day or self.today()
        start = current - timedelta(days=current.weekday())
        return start, start + timedelta(days=7)

    def open_tasks_today(self) -> int:
        """Count today's available open tasks."""
        today = self.today()
        return sum(
            task.date == today
            and task.status is TaskStatus.OPEN
            and not task.blocked
            for task in self._data.tasks.values()
        )

    def completed_tasks_today(self) -> int:
        """Count active task completions made today."""
        today = self.today()
        return sum(
            completion.active
            and dt_util.as_local(completion.completed_at).date() == today
            for completion in self._data.completions.values()
        )

    def automatic_tasks_today(self) -> int:
        """Count tasks created today by entity or automation integrations."""
        today = self.today()
        return sum(
            dt_util.as_local(task.created_at).date() == today
            and task.source in {TaskSource.ENTITY, TaskSource.AUTOMATION}
            and task.status is not TaskStatus.CANCELLED
            for task in self._data.tasks.values()
        )

    def completed_scheduled_tasks_today(self) -> int:
        """Count today's scheduled tasks that currently are completed."""
        today = self.today()
        return sum(
            task.date == today and task.status is TaskStatus.COMPLETED
            for task in self._data.tasks.values()
        )

    def points_by_participant(
        self,
        start: date,
        end: date,
        *,
        scoring_mode: ScoringMode | None = None,
        race_id: str | None = None,
    ) -> dict[str, int]:
        """Aggregate historical awarded points in [start, end)."""
        totals = {participant_id: 0 for participant_id in self._data.participants}
        for completion in self._data.completions.values():
            local_day = dt_util.as_local(completion.completed_at).date()
            if (
                completion.active
                and start <= local_day < end
                and (scoring_mode is None or completion.scoring_mode is scoring_mode)
                and (race_id is None or completion.race_id == race_id)
            ):
                totals[completion.participant_id] = (
                    totals.get(completion.participant_id, 0)
                    + completion.total_points_awarded
                )
                if completion.copilot_participant_id:
                    totals[completion.copilot_participant_id] = (
                        totals.get(completion.copilot_participant_id, 0)
                        + completion.copilot_points_awarded
                    )
        return totals

    def points_today(self) -> dict[str, int]:
        """Return today's participant totals."""
        today = self.today()
        return self.points_by_participant(today, today + timedelta(days=1))

    def points_week(self) -> dict[str, int]:
        """Return all current ISO-week participant totals."""
        start, end = self._week_bounds()
        return self.points_by_participant(start, end)

    def points_week_all(self) -> dict[str, int]:
        """Return all active completion points in the current week."""
        return self.points_week()

    def race_points_week(self, race_id: str | None = None) -> dict[str, int]:
        """Return only race-scored points in the current week."""
        start, end = self._week_bounds()
        return self.points_by_participant(
            start, end, scoring_mode=ScoringMode.RACE, race_id=race_id
        )

    def normal_points_week(self) -> dict[str, int]:
        """Return non-race points in the current week."""
        start, end = self._week_bounds()
        return self.points_by_participant(start, end, scoring_mode=ScoringMode.NORMAL)

    def week_leader(self) -> Participant | None:
        """Return one leader, or None for no points or a tie."""
        totals = self.race_points_week()
        if not totals or max(totals.values(), default=0) == 0:
            return None
        highest = max(totals.values())
        leaders = [key for key, points in totals.items() if points == highest]
        return self._data.participants[leaders[0]] if len(leaders) == 1 else None

    def state_snapshot(self) -> dict[str, Any]:
        """Return compact UI state without embedding full task lists."""
        today = self.today()
        total_today = sum(
            task.date == today and task.status is not TaskStatus.CANCELLED
            for task in self._data.tasks.values()
        )
        completed = self.completed_scheduled_tasks_today()
        leader = self.week_leader()
        return {
            "open_tasks_today": self.open_tasks_today(),
            "completed_tasks_today": completed,
            "automatic_tasks_today": self.automatic_tasks_today(),
            "team_progress": {"completed": completed, "total": total_today},
            "points_today": self.points_today(),
            "points_week": self.points_week(),
            "race_points_week": self.race_points_week(),
            "normal_points_week": self.normal_points_week(),
            "week_leader_id": leader.id if leader else None,
        }
