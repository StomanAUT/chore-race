"""Serializable domain models for Chore Race."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal, Self


class TaskStatus(StrEnum):
    """State of a concrete task."""

    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskSource(StrEnum):
    """Origin of a concrete task."""

    MANUAL = "manual"
    RECURRING = "recurring"
    ENTITY = "entity"
    AUTOMATION = "automation"
    CHAIN = "chain"


class ScoringMode(StrEnum):
    """Scoring context saved with a completion."""

    NORMAL = "normal"
    RACE = "race"


class RaceStatus(StrEnum):
    """Lifecycle state of a race session."""

    READY = "ready"
    RUNNING = "running"
    FINISHED = "finished"


class Difficulty(StrEnum):
    """Optional presentation difficulty."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(slots=True)
class Participant:
    """A household participant independent of HA users."""

    id: str
    name: str
    active: bool = True
    person_entity_id: str | None = None
    avatar: str | None = None
    sort_order: int = 0
    role: Literal["child", "adult"] = "child"
    can_do_restricted_tasks: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore a participant."""
        return cls(**data)


@dataclass(slots=True)
class ChoreType:
    """Reusable definition of household work."""

    id: str
    name: str
    default_race_points: int
    icon: str | None = None
    image: str | None = None
    streak_enabled: bool = False
    streak_max_bonus: int = 0
    default_copilot_points: int = 1
    active: bool = True
    difficulty: Difficulty | None = None
    adult_only: bool = False
    confirmation_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        data = asdict(self)
        if self.difficulty is not None:
            data["difficulty"] = self.difficulty.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore a chore type."""
        values = dict(data)
        if values.get("difficulty") is not None:
            values["difficulty"] = Difficulty(values["difficulty"])
        return cls(**values)


@dataclass(slots=True)
class ChoreTask:
    """A concrete, historically stable task."""

    id: str
    chore_type_id: str
    date: date
    race_points: int
    created_at: datetime
    updated_at: datetime
    area_id: str | None = None
    floor_id: str | None = None
    preferred_participant_id: str | None = None
    status: TaskStatus = TaskStatus.OPEN
    source: TaskSource = TaskSource.MANUAL
    source_entity_id: str | None = None
    chain_id: str | None = None
    chain_step_id: str | None = None
    blocked: bool = False
    base_race_points: int | None = None
    points_multiplier: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        data = asdict(self)
        data.update(
            {
                "date": self.date.isoformat(),
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
                "status": self.status.value,
                "source": self.source.value,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore a task."""
        values = dict(data)
        values["date"] = date.fromisoformat(values["date"])
        values["created_at"] = datetime.fromisoformat(values["created_at"])
        values["updated_at"] = datetime.fromisoformat(values["updated_at"])
        values["status"] = TaskStatus(values["status"])
        values["source"] = TaskSource(values["source"])
        return cls(**values)


@dataclass(slots=True)
class Completion:
    """Immutable scoring facts for one active task completion."""

    id: str
    task_id: str
    participant_id: str
    completed_at: datetime
    base_points_awarded: int
    total_points_awarded: int
    scoring_mode: ScoringMode
    fair_play_bonus: int = 0
    streak_bonus: int = 0
    copilot_participant_id: str | None = None
    copilot_points_awarded: int = 0
    race_id: str | None = None
    reverted_at: datetime | None = None

    @property
    def active(self) -> bool:
        """Return whether this completion contributes to totals."""
        return self.reverted_at is None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        data = asdict(self)
        data.update(
            {
                "completed_at": self.completed_at.isoformat(),
                "scoring_mode": self.scoring_mode.value,
                "reverted_at": (
                    self.reverted_at.isoformat() if self.reverted_at else None
                ),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore a completion."""
        values = dict(data)
        values["completed_at"] = datetime.fromisoformat(values["completed_at"])
        values["scoring_mode"] = ScoringMode(values["scoring_mode"])
        if values.get("reverted_at"):
            values["reverted_at"] = datetime.fromisoformat(values["reverted_at"])
        return cls(**values)


@dataclass(slots=True)
class Reward:
    """A winner-selectable household reward."""

    id: str
    name: str
    icon: str = "mdi:gift-outline"
    image: str | None = None
    active: bool = True
    sort_order: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore a reward."""
        return cls(**data)


@dataclass(slots=True)
class RewardSelection:
    """Immutable record of a champion's choice for one race."""

    id: str
    race_id: str
    reward_id: str
    participant_id: str
    selected_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        data = asdict(self)
        data["selected_at"] = self.selected_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore a reward selection."""
        values = dict(data)
        values["selected_at"] = datetime.fromisoformat(values["selected_at"])
        return cls(**values)


@dataclass(slots=True)
class Settings:
    """Persisted settings with race-ready defaults."""

    normal_completion_points: int = 1
    fair_play_bonus: int = 1
    race_enabled: bool = True
    race_duration_seconds: int = 1800
    race_weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    race_ready_time: str = "19:00"

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore settings."""
        return cls(**data)


@dataclass(slots=True)
class ChoreRaceData:
    """Complete persisted integration state."""

    schema_version: int = 1
    participants: dict[str, Participant] = field(default_factory=dict)
    chore_types: dict[str, ChoreType] = field(default_factory=dict)
    tasks: dict[str, ChoreTask] = field(default_factory=dict)
    completions: dict[str, Completion] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)
    race_sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    recurrence_rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_chains: dict[str, dict[str, Any]] = field(default_factory=dict)
    rewards: dict[str, Reward] = field(default_factory=dict)
    reward_selections: dict[str, RewardSelection] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible storage data."""
        return {
            "schema_version": self.schema_version,
            "participants": {
                key: value.to_dict() for key, value in self.participants.items()
            },
            "chore_types": {
                key: value.to_dict() for key, value in self.chore_types.items()
            },
            "tasks": {key: value.to_dict() for key, value in self.tasks.items()},
            "completions": {
                key: value.to_dict() for key, value in self.completions.items()
            },
            "settings": self.settings.to_dict(),
            "race_sessions": self.race_sessions,
            "recurrence_rules": self.recurrence_rules,
            "task_chains": self.task_chains,
            "rewards": {
                key: value.to_dict() for key, value in self.rewards.items()
            },
            "reward_selections": {
                key: value.to_dict()
                for key, value in self.reward_selections.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Restore integration state."""
        return cls(
            schema_version=data.get("schema_version", 1),
            participants={
                key: Participant.from_dict(value)
                for key, value in data.get("participants", {}).items()
            },
            chore_types={
                key: ChoreType.from_dict(value)
                for key, value in data.get("chore_types", {}).items()
            },
            tasks={
                key: ChoreTask.from_dict(value)
                for key, value in data.get("tasks", {}).items()
            },
            completions={
                key: Completion.from_dict(value)
                for key, value in data.get("completions", {}).items()
            },
            settings=Settings.from_dict(data.get("settings", {})),
            race_sessions=data.get("race_sessions", {}),
            recurrence_rules=data.get("recurrence_rules", {}),
            task_chains=data.get("task_chains", {}),
            rewards={
                key: Reward.from_dict(value)
                for key, value in data.get("rewards", {}).items()
            },
            reward_selections={
                key: RewardSelection.from_dict(value)
                for key, value in data.get("reward_selections", {}).items()
            },
        )
