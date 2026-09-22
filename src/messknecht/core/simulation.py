"""Simulation backend used when ``simulate=true`` is passed to ``initialize()``.

Design: every driver routes its I/O through the typed helpers of
:class:`~messknecht.core.instrument.VisaInstrument` (``query_float``,
``query_int``, ...). In simulation mode those helpers first ask the driver's
:class:`SimulationBackend` for a canned/stateful response; if the backend does
not handle the query, the typed helpers fall back to a fixed default value
plus a little noise (for floats). Operations that cannot be simulated in a
meaningful way raise :class:`~messknecht.core.exceptions.SimulationError`.

Simulation is a debugging aid, not a device model: values round-trip where
that is cheap (e.g. PSU setpoints), everything else is approximated.
"""

from __future__ import annotations

import random

SIM_DEFAULT_FLOAT = 1.0
SIM_FLOAT_NOISE = 1e-3


def sim_float(value: float = SIM_DEFAULT_FLOAT, noise: float = SIM_FLOAT_NOISE) -> float:
    """Return ``value`` with a little gaussian noise, for simulated readings."""
    return value + random.gauss(0.0, noise)


class SimulationBackend:
    """Base simulation backend: handles IEEE-488.2 common commands.

    Drivers subclass this (in the same module as the driver); most only override
    :attr:`IDN`. Writes are logged and ignored, and any query without a canned
    response returns ``None``, which lets the typed query helpers fall back to
    their default values. Override :meth:`handle_write` / :meth:`handle_query` /
    :meth:`handle_query_binary` only where a generic default will not do (e.g.
    the scope, which must return synthetic binary waveform/screenshot data).
    """

    IDN = "Messknecht,SimulatedInstrument,0,0.0"

    def __init__(self) -> None:
        self.state: dict[str, object] = {}
        self.reset()

    def reset(self) -> None:
        """Restore the simulated instrument state (``*RST``)."""
        self.state.clear()

    # -- hooks for driver specific backends ---------------------------------

    def handle_write(self, command: str) -> None:
        """Process a write. Default: ignore everything driver specific."""

    def handle_query(self, command: str) -> str | None:
        """Return a response string, or ``None`` if the query is not simulated."""
        return None

    def handle_query_binary(self, command: str) -> bytes | None:
        """Return binary block payload bytes, or ``None`` if not simulated."""
        return None

    # -- entry points used by SimulatedSession ------------------------------

    def write(self, command: str) -> None:
        normalized = command.strip().upper()
        if normalized == "*RST":
            self.reset()
            return
        if normalized in {"*CLS", "*OPC", "*WAI"}:
            return
        self.handle_write(command.strip())

    def query(self, command: str) -> str | None:
        normalized = command.strip().upper()
        common = {
            "*IDN?": self.IDN,
            "*OPC?": "1",
            "*ESR?": "0",
            "*STB?": "0",
            "*TST?": "0",
        }
        if normalized in common:
            return common[normalized]
        if normalized in {"SYST:ERR?", "SYSTEM:ERROR?", ":SYST:ERR?", ":SYSTEM:ERROR?"}:
            return '+0,"No error"'
        return self.handle_query(command.strip())


class SimulatedSession:
    """Stands in for the pyvisa resource when running in simulation mode.

    Attributes:
        backend: The driver specific :class:`SimulationBackend`.
        log: Every command sent (writes and queries), in order. Useful for
            debugging and for unit tests asserting on the SCPI traffic.
    """

    def __init__(self, backend: SimulationBackend) -> None:
        self.backend = backend
        self.log: list[str] = []
        self.timeout_ms: float = 0.0

    def write(self, command: str) -> None:
        self.log.append(command)
        self.backend.write(command)

    def query(self, command: str) -> str | None:
        self.log.append(command)
        return self.backend.query(command)

    def query_binary(self, command: str) -> bytes | None:
        self.log.append(command)
        return self.backend.handle_query_binary(command)
