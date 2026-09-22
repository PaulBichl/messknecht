"""Core building blocks: VISA base classes, options, exceptions, simulation."""

from __future__ import annotations

from messknecht.core.exceptions import (
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDataError,
    InstrumentError,
    InstrumentIOError,
    InstrumentTimeoutError,
    MessknechtError,
    NotInitializedError,
    OptionStringError,
    OverloadError,
    SimulationError,
)
from messknecht.core.instrument import InstrumentApplication, VisaInstrument
from messknecht.core.options import option_as_bool, option_as_float, parse_option_string
from messknecht.core.simulation import SimulatedSession, SimulationBackend, sim_float

__all__ = [
    "InstrumentApplication",
    "InstrumentCommandError",
    "InstrumentConnectionError",
    "InstrumentDataError",
    "InstrumentError",
    "InstrumentIOError",
    "InstrumentTimeoutError",
    "MessknechtError",
    "NotInitializedError",
    "OptionStringError",
    "OverloadError",
    "SimulatedSession",
    "SimulationBackend",
    "SimulationError",
    "VisaInstrument",
    "option_as_bool",
    "option_as_float",
    "parse_option_string",
    "sim_float",
]
