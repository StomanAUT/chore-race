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
    ScoringMode,
    Settings,
    TaskSource,
    TaskStatus,
)
from .scoring import calculate_completion_score
from .storage import ChoreRaceStore


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

    async def async_create_task(
        self,
        chore_type_id: str,
        task_date: date,
        *,
        area_id: str | None = None,
        race_points: int | None = None,
        preferred_participant_id: str | None = None,
        source: TaskSource | str = TaskSource.MANUAL,
        source_entity_id: str | None = None,
        chain_id: str | None = None,
        chain_step_id: str | None = None,
        blocked: bool = False,
    ) -> ChoreTask:
        """Create a concrete task with point values snapshotted now."""
        async with self._mutation_lock:
            chore_type = self._data.chore_types.get(chore_type_id)
            if chore_type is None:
                raise NotFoundError("Chore type not found")
            if preferred_participant_id is not None:
                self._require_participant(preferred_participant_id)
            if area_id is not None:
                registry = ar.async_get(self.hass)
                if registry.async_get_area(area_id) is None:
                    raise ValidationError("Home Assistant area does not exist")
            source = TaskSource(source)
            if source is TaskSource.ENTITY and not source_entity_id:
                raise ValidationError("Entity tasks require source_entity_id")
            now = dt_util.utcnow()
            task = ChoreTask(
                id=self._new_id(),
                chore_type_id=chore_type_id,
                area_id=area_id,
                date=task_date,
                race_points=self._validate_points(
                    chore_type.default_race_points
                    if race_points is None
                    else race_points,
                    "race_points",
                ),
                preferred_participant_id=preferred_participant_id,
                source=source,
                source_entity_id=source_entity_id,
                chain_id=chain_id,
                chain_step_id=chain_step_id,
                blocked=blocked,
                created_at=now,
                updated_at=now,
            )
            self._data.tasks[task.id] = task
            await self._async_commit()
            self.hass.bus.async_fire(EVENT_TASK_CREATED, {"task_id": task.id})
            return task

    async def async_create_recurrence_rule(
        self,
        chore_type_id: str,
        start_date: date,
        *,
        frequency: str,
        interval: int = 1,
        area_id: str | None = None,
        preferred_participant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a recurrence rule and materialize its first due task."""
        if frequency not in {"days", "monthly", "yearly"}:
            raise ValidationError("frequency must be days, monthly or yearly")
        if isinstance(interval, bool) or not 1 <= interval <= 365:
            raise ValidationError("interval must be between 1 and 365")
        if chore_type_id not in self._data.chore_types:
            raise NotFoundError("Chore type not found")
        if preferred_participant_id is not None:
            self._require_participant(preferred_participant_id)
        if (
            area_id is not None
            and ar.async_get(self.hass).async_get_area(area_id) is None
        ):
            raise ValidationError("Home Assistant area does not exist")
        rule = {
            "id": self._new_id(),
            "chore_type_id": chore_type_id,
            "start_date": start_date.isoformat(),
            "frequency": frequency,
            "interval": interval,
            "area_id": area_id,
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
            "area_id",
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
                and changes["frequency"] not in {"days", "monthly", "yearly"}
            ):
                raise ValidationError("frequency must be days, monthly or yearly")
            if "interval" in changes:
                interval = changes["interval"]
                if isinstance(interval, bool) or not 1 <= interval <= 365:
                    raise ValidationError("interval must be between 1 and 365")
            if changes.get("preferred_participant_id") is not None:
                self._require_participant(changes["preferred_participant_id"])
            if (
                changes.get("area_id") is not None
                and ar.async_get(self.hass).async_get_area(changes["area_id"]) is None
            ):
                raise ValidationError("Home Assistant area does not exist")
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
    def _rule_is_due(rule: dict[str, Any], day: date) -> bool:
        start = date.fromisoformat(rule["start_date"])
        if day < start:
            return False
        frequency = rule["frequency"]
        if frequency == "days":
            return (day - start).days % int(rule.get("interval", 1)) == 0
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
            if changes.get("preferred_participant_id") is not None:
                self._require_participant(changes["preferred_participant_id"])
            if "race_points" in changes:
                changes["race_points"] = self._validate_points(
                    changes["race_points"], "race_points"
                )
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
        self, task_id: str, participant_id: str
    ) -> Completion:
        """Atomically complete a task once and award normal or race points."""
        async with self._mutation_lock:
            task = self._require_task(task_id)
            participant = self._require_participant(participant_id)
            chore_type = self._data.chore_types[task.chore_type_id]
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
            race_id = race["id"] if race is not None else None
            score = calculate_completion_score(
                task, self._data.settings, race_id=race_id
            )
            completion = Completion(
                id=self._new_id(),
                task_id=task.id,
                participant_id=participant.id,
                completed_at=now,
                base_points_awarded=score.base,
                fair_play_bonus=score.fair_play,
                streak_bonus=score.streak,
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
                },
            )
            return completion

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
                "started_at": now.isoformat(),
                "ends_at": (
                    now
                    + timedelta(
                        seconds=self._data.settings.race_duration_seconds
                    )
                ).isoformat(),
                "finished_at": None,
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
            return {
                "status": RaceStatus.READY.value,
                "race_id": None,
                "started_at": None,
                "ends_at": None,
                "remaining_seconds": 0,
                "leaderboard": [],
            }
        ends_at = datetime.fromisoformat(race["ends_at"])
        remaining = max(0, int((ends_at - current).total_seconds()))
        status = race["status"]
        if status == RaceStatus.RUNNING and remaining == 0:
            status = RaceStatus.FINISHED.value
        if status != RaceStatus.RUNNING:
            remaining = 0
        totals = self.race_points_week(race["id"])
        leaderboard = sorted(
            (
                {
                    "participant_id": participant.id,
                    "name": participant.name,
                    "points": totals.get(participant.id, 0),
                }
                for participant in self._data.participants.values()
                if participant.active
            ),
            key=lambda item: (-item["points"], item["name"].casefold()),
        )
        return {
            "status": status,
            "race_id": race["id"],
            "started_at": race["started_at"],
            "ends_at": race["ends_at"],
            "remaining_seconds": remaining,
            "leaderboard": leaderboard,
        }

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
        """Reject edits that could rewrite completion or live-race history."""
        if task.status is not TaskStatus.OPEN:
            raise ConflictError("Only open tasks can be changed")
        if any(
            completion.task_id == task.id
            for completion in self._data.completions.values()
        ):
            raise ConflictError("Tasks with completion history cannot be changed")
        if task.date == self.today() and self._active_race() is not None:
            raise ConflictError("Today's tasks cannot be changed during a race")

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
            "team_progress": {"completed": completed, "total": total_today},
            "points_today": self.points_today(),
            "points_week": self.points_week(),
            "race_points_week": self.race_points_week(),
            "normal_points_week": self.normal_points_week(),
            "week_leader_id": leader.id if leader else None,
        }
