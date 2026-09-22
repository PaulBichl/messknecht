"""Exception hierarchy of the messknecht library.

All errors raised by messknecht derive from :class:`MessknechtError`, so a
user can catch every library error with a single ``except MessknechtError``.
Invalid *arguments* passed by the user (wrong channel number, value out of
range, ...) raise the standard :class:`ValueError` / :class:`TypeError`
instead, following normal Python semantics.
"""

from __future__ import annotations


class MessknechtError(Exception):
    """Base class for all messknecht errors."""


class OptionStringError(MessknechtError, ValueError):
    """The option string passed to ``initialize()`` could not be parsed."""


class InstrumentError(MessknechtError):
    """Base class for all instrument related errors."""


class NotInitializedError(InstrumentError):
    """An operation was attempted before ``initialize()`` was called."""


class InstrumentConnectionError(InstrumentError):
    """The VISA session could not be opened or was lost."""


class InstrumentTimeoutError(InstrumentError):
    """The instrument did not answer within the VISA timeout."""


class InstrumentIOError(InstrumentError):
    """Low level VISA read/write failed (other than a timeout)."""


class InstrumentCommandError(InstrumentError):
    """The instrument reported one or more errors in its error queue.

    Attributes:
        errors: The raw error messages read from the instrument.
    """

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors: list[str] = errors or []


class InstrumentDataError(InstrumentError):
    """A response from the instrument could not be parsed."""


class OverloadError(InstrumentError):
    """A measurement returned the overload indicator (e.g. +9.9E+37)."""


class SimulationError(InstrumentError):
    """The requested operation is not supported in simulation mode."""
