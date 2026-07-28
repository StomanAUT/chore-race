"""Central scoring policy for Chore Race."""

from dataclasses import dataclass

from .models import ChoreTask, ScoringMode, Settings


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
    settings: Settings,
    *,
    race_id: str | None = None,
) -> Score:
    """Calculate a completion score in exactly one central place.

    Milestone 1 has no active race engine, but the explicit race branch keeps
    future score changes away from service, API, entity and UI layers.
    """
    if race_id is None:
        return Score(
            mode=ScoringMode.NORMAL,
            base=settings.normal_completion_points,
        )
    return Score(mode=ScoringMode.RACE, base=task.race_points)
