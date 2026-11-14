"""Exception hierarchy shared by the whole project.

Messages are in Portuguese because they reach the user interface verbatim.
"""

from __future__ import annotations


class CircuitosError(Exception):
    """Base class for every error raised by the project."""


class UnitError(CircuitosError, ValueError):
    """A value has no unit, or its unit has the wrong dimension."""


class DataIntegrityError(CircuitosError):
    """Component or project data violates a traceability or schema rule."""


class SimulationError(CircuitosError):
    """The simulator could not run or produced no usable result."""

    def __init__(self, message: str, *, log: str = "", suggestions: list[str] | None = None):
        super().__init__(message)
        self.log = log
        self.suggestions = suggestions or []


class ConvergenceError(SimulationError):
    """The simulator ran but did not converge."""


class SimulatorUnavailableError(SimulationError):
    """No simulator backend could be loaded on this machine."""


class SimulationCancelledError(SimulationError):
    """The user cancelled the simulation."""
