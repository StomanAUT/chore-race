"""Domain errors for Chore Race."""

from typing import ClassVar


class ChoreRaceError(Exception):
    """Base integration error."""

    code: ClassVar[str] = "chore_race_error"


class NotFoundError(ChoreRaceError):
    """Referenced record does not exist."""

    code = "not_found"


class ConflictError(ChoreRaceError):
    """Requested transition conflicts with current state."""

    code = "conflict"


class ValidationError(ChoreRaceError):
    """Input violates a domain rule."""

    code = "validation_error"
