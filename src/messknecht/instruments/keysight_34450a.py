"""Driver for the Keysight 34450A 5.5 digit digital multimeter.

Trigger model (manual, "Triggering the Multimeter"): remotely the DMM makes
one measurement per trigger. This driver exposes that as a *continuous* flag
on every ``configure.*`` method:

* ``continuous=True`` (default): trigger source ``IMMediate``; every call to
  :meth:`Keysight34450A.read` sends ``READ?`` and returns a fresh reading.
* ``continuous=False``: trigger source ``BUS``; a measurement is armed with
  :meth:`~Keysight34450A.initiate` and fired with software triggers. In this
  mode :meth:`~Keysight34450A.read` performs ``INITiate`` + ``*TRG`` +
  ``FETCh?`` for one on-demand reading.

Note: ``CONFigure`` resets the trigger source to ``IMMediate`` (manual), so
the flag is applied after each configuration - configure first, then read.

Usage::

    from messknecht import Keysight34450A

    with Keysight34450A() as dmm:
        dmm.initialize("USB0::0x2A8D::...::INSTR", reset=True)
        dmm.configure.voltage_dc(range=10, resolution=1.5e-6)
        print(dmm.read())
"""

from __future__ import annotations

import contextlib

from messknecht.core.exceptions import OverloadError
from messknecht.core.instrument import InstrumentApplication, VisaInstrument
from messknecht.core.scpi import scpi_value
from messknecht.core.simulation import SimulationBackend

#: Absolute values at or above this indicate overload (manual: +/-9.9E+37).
OVERLOAD_THRESHOLD = 9.0e37

_RANGE_KEYWORDS = ("AUTO", "MIN", "MAX", "DEF")
_RESOLUTION_KEYWORDS = ("MIN", "MAX", "DEF")
_TRIGGER_SOURCES = ("IMMEDIATE", "BUS", "EXTERNAL", "IMM", "EXT")


class _Keysight34450ASimulation(SimulationBackend):
    """Generic simulation stub: ``*IDN?`` and a canned ``CONFigure?`` response.

    Writes are logged and ignored; ``READ?``/``FETCh?`` fall back to the
    :meth:`~VisaInstrument.query_float` default.
    """

    IDN = "Keysight Technologies,34450A,MYSIM00001,01.00-01.00"
    #: Manual page 62: quoted function, range and resolution. Not derived from
    #: the last ``CONFigure`` write - the simulation does not model the state.
    CONFIGURATION = '"VOLT +1.000000E+01,+3.000000E-05"'

    def handle_query(self, command: str) -> str | None:
        if command.strip().upper() in {"CONF?", "CONFIGURE?"}:
            return self.CONFIGURATION
        return None


class Keysight34450ALowLevel(VisaInstrument):
    """Low level SCPI wrapper for the Keysight 34450A."""

    SIMULATION_BACKEND = _Keysight34450ASimulation

    # -- CONFigure subsystem -------------------------------------------------

    def _configure(self, function: str, range_value: float | str | None, resolution: float | str | None) -> None:
        command = f"CONFigure:{function}"
        if range_value is not None:
            command += f" {scpi_value(range_value, _RANGE_KEYWORDS)}"
            if resolution is not None:
                command += f",{scpi_value(resolution, _RESOLUTION_KEYWORDS)}"
        elif resolution is not None:
            msg = "A resolution can only be given together with a range"
            raise ValueError(msg)
        self.write(command)

    def configure_voltage_dc(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary][:VOLTage][:DC] [<range>[,<resolution>]]``."""
        self._configure("VOLTage:DC", range_value, resolution)

    def configure_voltage_ac(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary][:VOLTage]:AC [<range>[,<resolution>]]``."""
        self._configure("VOLTage:AC", range_value, resolution)

    def configure_current_dc(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary]:CURRent[:DC] [<range>[,<resolution>]]``."""
        self._configure("CURRent:DC", range_value, resolution)

    def configure_current_ac(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary]:CURRent:AC [<range>[,<resolution>]]``."""
        self._configure("CURRent:AC", range_value, resolution)

    def configure_resistance(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary]:RESistance [<range>[,<resolution>]]`` (2-wire)."""
        self._configure("RESistance", range_value, resolution)

    def configure_resistance_4wire(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary]:FRESistance [<range>[,<resolution>]]`` (4-wire)."""
        self._configure("FRESistance", range_value, resolution)

    def configure_frequency(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary]:FREQuency [<range>[,<resolution>]]``."""
        self._configure("FREQuency", range_value, resolution)

    def configure_capacitance(
        self, range_value: float | str | None = None, resolution: float | str | None = None
    ) -> None:
        """``CONFigure[:PRIMary]:CAPacitance [<range>[,<resolution>]]``."""
        self._configure("CAPacitance", range_value, resolution)

    def configure_continuity(self) -> None:
        """``CONFigure[:PRIMary]:CONTinuity``."""
        self.write("CONFigure:CONTinuity")

    def configure_diode(self) -> None:
        """``CONFigure[:PRIMary]:DIODe``."""
        self.write("CONFigure:DIODe")

    def get_configuration(self) -> str:
        """``CONFigure?`` - return the present function, range and resolution."""
        return self.query("CONFigure?")

    # -- trigger subsystem -----------------------------------------------------

    def set_trigger_source(self, source: str) -> None:
        """``TRIGger:SOURce {IMMediate|BUS|EXTernal}``."""
        keyword = source.strip().upper()
        if keyword not in _TRIGGER_SOURCES:
            msg = f"Invalid trigger source {source!r}; allowed: IMMediate, BUS, EXTernal"
            raise ValueError(msg)
        self.write(f"TRIGger:SOURce {keyword}")

    def get_trigger_source(self) -> str:
        """``TRIGger:SOURce?``."""
        return self.query("TRIGger:SOURce?")

    def set_trigger_delay(self, seconds: float | str) -> None:
        """``TRIGger:DELay {<seconds>|MIN|MAX|DEF}``."""
        self.write(f"TRIGger:DELay {scpi_value(seconds, _RESOLUTION_KEYWORDS)}")

    def trigger(self) -> None:
        """``*TRG`` - software trigger (instrument must be in wait-for-trigger)."""
        self.write("*TRG")

    # -- measurement flow --------------------------------------------------------

    def initiate(self) -> None:
        """``INITiate`` - go from idle to wait-for-trigger state."""
        self.write("INITiate")

    def abort(self) -> None:
        """``ABORt`` - abort the measurement in progress, return to idle."""
        self.write("ABORt")

    def read_measurement(self) -> float:
        """``READ?`` - trigger a measurement and return the reading."""
        return self.query_float("READ?")

    def fetch(self) -> float:
        """``FETCh?`` - transfer the reading from memory to the output buffer."""
        return self.query_float("FETCh?")


class Keysight34450AConfigure:
    """The ``dmm.configure`` namespace: one method per measurement function.

    Every method resets the measurement and trigger parameters (``CONFigure``
    semantics), applies the requested trigger mode and checks the instrument
    error queue.
    """

    def __init__(self, dmm: Keysight34450A) -> None:
        self._dmm = dmm

    def _finish(self, continuous: bool) -> None:
        lowlevel = self._dmm.lowlevel
        self._dmm._continuous = continuous
        if not continuous:
            lowlevel.set_trigger_source("BUS")
        # continuous: CONFigure already set the trigger source to IMMediate.
        lowlevel.check_errors()

    def voltage_dc(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure DC voltage measurement.

        Args:
            range: Range in Volts (0.1, 1, 10, 100, 1000) or "AUTO"/"MIN"/"MAX"/"DEF".
                ``None`` uses auto range.
            resolution: Resolution (3.00e-5, 2.00e-5, 1.50e-6) or "MIN"/"MAX"/"DEF".
                Only allowed with a fixed range.
            continuous: See module docstring; ``True`` = immediate trigger.
        """
        self._dmm.lowlevel.configure_voltage_dc(range, resolution)
        self._finish(continuous)

    def voltage_ac(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure AC voltage measurement."""
        self._dmm.lowlevel.configure_voltage_ac(range, resolution)
        self._finish(continuous)

    def current_dc(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure DC current measurement."""
        self._dmm.lowlevel.configure_current_dc(range, resolution)
        self._finish(continuous)

    def current_ac(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure AC current measurement."""
        self._dmm.lowlevel.configure_current_ac(range, resolution)
        self._finish(continuous)

    def resistance(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure 2-wire resistance measurement."""
        self._dmm.lowlevel.configure_resistance(range, resolution)
        self._finish(continuous)

    def resistance_4wire(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure 4-wire resistance measurement."""
        self._dmm.lowlevel.configure_resistance_4wire(range, resolution)
        self._finish(continuous)

    def frequency(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure frequency measurement."""
        self._dmm.lowlevel.configure_frequency(range, resolution)
        self._finish(continuous)

    def capacitance(
        self,
        range: float | str | None = None,
        resolution: float | str | None = None,
        continuous: bool = True,
    ) -> None:
        """Configure capacitance measurement."""
        self._dmm.lowlevel.configure_capacitance(range, resolution)
        self._finish(continuous)

    def continuity(self, continuous: bool = True) -> None:
        """Configure continuity test."""
        self._dmm.lowlevel.configure_continuity()
        self._finish(continuous)

    def diode(self, continuous: bool = True) -> None:
        """Configure diode test."""
        self._dmm.lowlevel.configure_diode()
        self._finish(continuous)


class Keysight34450A(InstrumentApplication[Keysight34450ALowLevel]):
    """Application layer for the Keysight 34450A digital multimeter."""

    def __init__(self) -> None:
        super().__init__(Keysight34450ALowLevel())
        #: Configuration namespace: ``dmm.configure.voltage_dc(...)`` etc.
        self.configure = Keysight34450AConfigure(self)
        self._continuous = True

    @property
    def continuous(self) -> bool:
        """Trigger mode selected by the last ``configure.*`` call."""
        return self._continuous

    @staticmethod
    def _check_overload(value: float) -> float:
        if abs(value) >= OVERLOAD_THRESHOLD:
            msg = f"Measurement overload (instrument returned {value:+.1E})"
            raise OverloadError(msg)
        return value

    def read(self, timeout_ms: float | None = None) -> float:
        """Take one measurement and return the reading.

        In continuous mode this sends ``READ?``. In triggered (BUS) mode it
        arms the instrument, fires a software trigger and fetches the result.

        Args:
            timeout_ms: Optional VISA timeout just for this reading (long
                integration times and auto ranging can exceed the default).

        Raises:
            OverloadError: If the input exceeds the selected range.
        """
        lowlevel = self._lowlevel
        timeout_context = lowlevel.temporary_timeout(timeout_ms) if timeout_ms is not None else contextlib.nullcontext()
        with timeout_context:
            if self._continuous:
                value = lowlevel.read_measurement()
            else:
                lowlevel.initiate()
                lowlevel.trigger()
                value = lowlevel.fetch()
        return self._check_overload(value)

    def fetch(self) -> float:
        """Return the last reading from memory (``FETCh?``) without triggering."""
        return self._check_overload(self._lowlevel.fetch())

    def initiate(self) -> None:
        """Arm the instrument (idle -> wait-for-trigger)."""
        self._lowlevel.initiate()

    def trigger(self) -> None:
        """Send a software trigger (``*TRG``); requires BUS trigger source and an armed instrument."""
        self._lowlevel.trigger()

    def abort(self) -> None:
        """Abort a measurement in progress and return to idle."""
        self._lowlevel.abort()
