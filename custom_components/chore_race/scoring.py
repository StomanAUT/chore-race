"""Central scoring policy for Chore Race."""

from dataclasses import dataclass

from .models import ChoreTask, ChoreType, ScoringMode, Settings


@dataclass(frozen=True, slots=True)
class Score:
    """Snapshot of points awarded by a completion."""

    mode: ScoringMode
    base: int
    fair_play: int = 0
    streak: int = 0
    copilot: int = 0

    @property
    def total(self) -> int:
        """Return driver points; copilot points belong to the copilot."""
        return self.base + self.fair_play + self.streak


def calculate_completion_score(
    task: ChoreTask,
    chore_type: ChoreType,
    settings: Settings,
    *,
    race_id: str | None = None,
    fair_play: bool = False,
    has_copilot: bool = False,
    streak_length: int = 0,
) -> Score:
    """Calculate a completion score in exactly one central place.

    The manager passes a race ID only while a race session is active, keeping
    scoring policy away from service, API, entity and UI layers.
    """
    if race_id is None:
        return Score(
            mode=ScoringMode.NORMAL,
            base=settings.normal_completion_points,
        )
    return Score(
        mode=ScoringMode.RACE,
        base=task.race_points,
        fair_play=settings.fair_play_bonus if fair_play else 0,
        streak=(
            min(max(streak_length, 0), chore_type.streak_max_bonus)
            if chore_type.streak_enabled
            else 0
        ),
        copilot=chore_type.default_copilot_points if has_copilot else 0,
    )
