"""messknecht - lab automation: instrument drivers on top of pyvisa.

Quick start::

    from messknecht import TTiPL303QMD

    with TTiPL303QMD() as psu:
        psu.initialize("USB0::...::INSTR", reset=True)
        psu.ch1.configure(voltage=5.0, current_limit=0.5, output=True)
"""

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
from messknecht.instruments.keysight_33500b import Keysight33500B, Keysight33500BLowLevel
from messknecht.instruments.keysight_34450a import Keysight34450A, Keysight34450ALowLevel
from messknecht.instruments.keysight_dsox3000t import (
    KeysightDSOX3000T,
    KeysightDSOX3000TLowLevel,
    ScopeWaveform,
)
from messknecht.instruments.tti_pl303qmd import CurrentRange, TTiPL303QMD, TTiPL303QMDLowLevel

__version__ = "0.1.0"

__all__ = [
    "CurrentRange",
    "InstrumentApplication",
    "InstrumentCommandError",
    "InstrumentConnectionError",
    "InstrumentDataError",
    "InstrumentError",
    "InstrumentIOError",
    "InstrumentTimeoutError",
    "Keysight33500B",
    "Keysight33500BLowLevel",
    "Keysight34450A",
    "Keysight34450ALowLevel",
    "KeysightDSOX3000T",
    "KeysightDSOX3000TLowLevel",
    "MessknechtError",
    "NotInitializedError",
    "OptionStringError",
    "OverloadError",
    "ScopeWaveform",
    "SimulationError",
    "TTiPL303QMD",
    "TTiPL303QMDLowLevel",
    "VisaInstrument",
    "__version__",
]
