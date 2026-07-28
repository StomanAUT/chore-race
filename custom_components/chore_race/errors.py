"""Domain errors for Chore Race."""


class ChoreRaceError(Exception):
    """Base integration error."""


class NotFoundError(ChoreRaceError):
    """Referenced record does not exist."""


class ConflictError(ChoreRaceError):
    """Requested transition conflicts with current state."""


class ValidationError(ChoreRaceError):
    """Input violates a domain rule."""
