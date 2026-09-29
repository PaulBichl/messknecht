"""Driver for the Keysight 33500B series waveform generators.

Covers standard waveform configuration (sine, square, ramp, pulse, noise, DC),
frequency sweep, burst and downloading arbitrary waveforms, e.g. from a CSV file. Two channel models
(33510B/33522B, ...) are supported via the ``channel`` argument; single
channel models simply use channel 1.

Arbitrary waveform download follows the manual's "Download Arbitrary Waveform
as ASCII" example program: values are normalized to -1..+1 and sent with
``SOURce<n>:DATA:ARBitrary <name>,<v1>,<v2>,...``.

Usage::

    from messknecht import Keysight33500B

    with Keysight33500B() as wfg:
        wfg.initialize("TCPIP0::192.168.1.20::INSTR", reset=True)
        wfg.configure_sine(frequency=1e3, amplitude=2.0, offset=0.0)
        wfg.output(True)
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

from messknecht.core.instrument import InstrumentApplication, VisaInstrument
from messknecht.core.scpi import scpi_bool, scpi_number
from messknecht.core.simulation import SimulationBackend

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Arbitrary waveform size limits of the 33500B series (points).
ARB_MIN_POINTS = 8
ARB_MAX_POINTS = 1_000_000

#: Waveform phase offset range (degrees).
PHASE_MIN_DEGREES = -360.0
PHASE_MAX_DEGREES = 360.0

#: Output termination range (Ohm); anything else must be INFinity (high Z).
LOAD_MIN_OHMS = 1.0
LOAD_MAX_OHMS = 10_000.0
#: ``OUTPut<n>:LOAD?`` answers high Z with 9.9E+37; values above this mean infinite.
_LOAD_INFINITE_THRESHOLD = 9.0e37
#: Spellings for "high impedance" accepted by the application layer.
_HIGH_Z_KEYWORDS = {"HIGHZ", "HIGH_Z", "HI-Z", "HIZ", "INF", "INFINITY"}

_SWEEP_SPACINGS = {"LIN": "LINear", "LINEAR": "LINear", "LOG": "LOGarithmic", "LOGARITHMIC": "LOGarithmic"}
_BURST_MODES = {"TRIG": "TRIGgered", "TRIGGERED": "TRIGgered", "GAT": "GATed", "GATED": "GATed"}
_TRIGGER_SOURCES = {
    "IMM": "IMMediate",
    "IMMEDIATE": "IMMediate",
    "EXT": "EXTernal",
    "EXTERNAL": "EXTernal",
    "TIM": "TIMer",
    "TIMER": "TIMer",
    "BUS": "BUS",
}

_ARB_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,11}")
_STANDARD_FUNCTIONS = ("SINusoid", "SQUare", "RAMP", "PULSe", "NOISe", "DC", "PRBS", "ARB")
#: Accepted spellings: full mnemonic and SCPI short form (upper case part).
_FUNCTION_KEYWORDS = {name.upper() for name in _STANDARD_FUNCTIONS} | {
    "".join(char for char in name if char.isupper()) for name in _STANDARD_FUNCTIONS
}


class _Keysight33500BSimulation(SimulationBackend):
    """Generic simulation stub: only overrides ``*IDN?`` for this model.

    Writes are logged and ignored; numeric reads (frequency, amplitude, ...)
    fall back to the typed-query defaults. ``FUNCtion?`` and other string
    queries are not simulated.
    """

    IDN = "Keysight Technologies,33522B,MYSIM00001,1.00-1.00-1.00-1.00"


class Keysight33500BLowLevel(VisaInstrument):
    """Low level SCPI wrapper for the Keysight 33500B series."""

    SIMULATION_BACKEND = _Keysight33500BSimulation
    ID_PATTERN = r"335\d\dB"

    @staticmethod
    def _source(channel: int) -> str:
        if channel not in (1, 2):
            msg = f"Channel must be 1 or 2, got {channel}"
            raise ValueError(msg)
        return f"SOURce{channel}"

    # -- standard waveforms ---------------------------------------------------

    def set_function(self, channel: int, function: str) -> None:
        """``[SOURce<n>:]FUNCtion {SIN|SQU|RAMP|PULS|NOIS|DC|PRBS|ARB}``."""
        keyword = function.strip().upper()
        if keyword not in _FUNCTION_KEYWORDS:
            msg = f"Invalid function {function!r}; allowed: {', '.join(_STANDARD_FUNCTIONS)}"
            raise ValueError(msg)
        self.write(f"{self._source(channel)}:FUNCtion {keyword}")

    def get_function(self, channel: int) -> str:
        """``[SOURce<n>:]FUNCtion?``."""
        return self.query(f"{self._source(channel)}:FUNCtion?")

    def set_frequency(self, channel: int, hertz: float) -> None:
        """``[SOURce<n>:]FREQuency <frequency>``."""
        self.write(f"{self._source(channel)}:FREQuency {scpi_number(hertz)}")

    def get_frequency(self, channel: int) -> float:
        """``[SOURce<n>:]FREQuency?``."""
        return self.query_float(f"{self._source(channel)}:FREQuency?", sim_value=1000.0)

    def set_amplitude(self, channel: int, volts_pp: float) -> None:
        """``[SOURce<n>:]VOLTage <amplitude>`` (unit: Vpp by default)."""
        self.write(f"{self._source(channel)}:VOLTage {scpi_number(volts_pp)}")

    def get_amplitude(self, channel: int) -> float:
        """``[SOURce<n>:]VOLTage?``."""
        return self.query_float(f"{self._source(channel)}:VOLTage?", sim_value=0.1)

    def set_offset(self, channel: int, volts: float) -> None:
        """``[SOURce<n>:]VOLTage:OFFSet <voltage>``."""
        self.write(f"{self._source(channel)}:VOLTage:OFFSet {scpi_number(volts)}")

    def get_offset(self, channel: int) -> float:
        """``[SOURce<n>:]VOLTage:OFFSet?``."""
        return self.query_float(f"{self._source(channel)}:VOLTage:OFFSet?", sim_value=0.0)

    def set_phase(self, channel: int, degrees: float) -> None:
        """``[SOURce<n>:]PHASe <angle>`` (unit per ``UNIT:ANGLe``, default degrees)."""
        self.write(f"{self._source(channel)}:PHASe {scpi_number(degrees)}")

    def get_phase(self, channel: int) -> float:
        """``[SOURce<n>:]PHASe?``."""
        return self.query_float(f"{self._source(channel)}:PHASe?", sim_value=0.0)

    def set_square_duty_cycle(self, channel: int, percent: float) -> None:
        """``[SOURce<n>:]FUNCtion:SQUare:DCYCle <percent>``."""
        self.write(f"{self._source(channel)}:FUNCtion:SQUare:DCYCle {scpi_number(percent)}")

    def set_ramp_symmetry(self, channel: int, percent: float) -> None:
        """``[SOURce<n>:]FUNCtion:RAMP:SYMMetry <percent>``."""
        self.write(f"{self._source(channel)}:FUNCtion:RAMP:SYMMetry {scpi_number(percent)}")

    def set_pulse_width(self, channel: int, seconds: float) -> None:
        """``[SOURce<n>:]FUNCtion:PULSe:WIDTh <seconds>``."""
        self.write(f"{self._source(channel)}:FUNCtion:PULSe:WIDTh {scpi_number(seconds)}")

    def set_pulse_duty_cycle(self, channel: int, percent: float) -> None:
        """``[SOURce<n>:]FUNCtion:PULSe:DCYCle <percent>``."""
        self.write(f"{self._source(channel)}:FUNCtion:PULSe:DCYCle {scpi_number(percent)}")

    def set_pulse_edge_time(self, channel: int, seconds: float) -> None:
        """``[SOURce<n>:]FUNCtion:PULSe:TRANsition[:BOTH] <seconds>``."""
        self.write(f"{self._source(channel)}:FUNCtion:PULSe:TRANsition:BOTH {scpi_number(seconds)}")

    # -- sweep -----------------------------------------------------------------

    def set_sweep_state(self, channel: int, on: bool) -> None:
        """``[SOURce<n>:]SWEep:STATe {ON|OFF}``."""
        self.write(f"{self._source(channel)}:SWEep:STATe {scpi_bool(on)}")

    def set_start_frequency(self, channel: int, hertz: float) -> None:
        """``[SOURce<n>:]FREQuency:STARt <frequency>``."""
        self.write(f"{self._source(channel)}:FREQuency:STARt {scpi_number(hertz)}")

    def set_stop_frequency(self, channel: int, hertz: float) -> None:
        """``[SOURce<n>:]FREQuency:STOP <frequency>``."""
        self.write(f"{self._source(channel)}:FREQuency:STOP {scpi_number(hertz)}")

    def set_sweep_time(self, channel: int, seconds: float) -> None:
        """``[SOURce<n>:]SWEep:TIME <seconds>``."""
        self.write(f"{self._source(channel)}:SWEep:TIME {scpi_number(seconds)}")

    def set_sweep_spacing(self, channel: int, spacing: str) -> None:
        """``[SOURce<n>:]SWEep:SPACing {LINear|LOGarithmic}``."""
        keyword = _keyword(spacing, _SWEEP_SPACINGS, "sweep spacing")
        self.write(f"{self._source(channel)}:SWEep:SPACing {keyword}")

    # -- burst -----------------------------------------------------------------

    def set_burst_state(self, channel: int, on: bool) -> None:
        """``[SOURce<n>:]BURSt:STATe {ON|OFF}``."""
        self.write(f"{self._source(channel)}:BURSt:STATe {scpi_bool(on)}")

    def set_burst_mode(self, channel: int, mode: str) -> None:
        """``[SOURce<n>:]BURSt:MODE {TRIGgered|GATed}``."""
        keyword = _keyword(mode, _BURST_MODES, "burst mode")
        self.write(f"{self._source(channel)}:BURSt:MODE {keyword}")

    def set_burst_cycles(self, channel: int, cycles: int | str) -> None:
        """``[SOURce<n>:]BURSt:NCYCles {<cycles>|INFinity}``."""
        if isinstance(cycles, str):
            if cycles.strip().upper() not in {"INF", "INFINITY"}:
                msg = f"Invalid burst cycles {cycles!r}; use a count >= 1 or 'infinity'"
                raise ValueError(msg)
            value = "INFinity"
        else:
            if cycles < 1:
                msg = f"Burst cycles must be >= 1, got {cycles}"
                raise ValueError(msg)
            value = str(int(cycles))
        self.write(f"{self._source(channel)}:BURSt:NCYCles {value}")

    def set_burst_period(self, channel: int, seconds: float) -> None:
        """``[SOURce<n>:]BURSt:INTernal:PERiod <seconds>`` - used with an immediate trigger."""
        self.write(f"{self._source(channel)}:BURSt:INTernal:PERiod {scpi_number(seconds)}")

    # -- trigger (sweep/burst) -------------------------------------------------

    def set_trigger_source(self, channel: int, source: str) -> None:
        """``TRIGger<n>:SOURce {IMMediate|EXTernal|TIMer|BUS}``."""
        self._source(channel)
        keyword = _keyword(source, _TRIGGER_SOURCES, "trigger source")
        self.write(f"TRIGger{channel}:SOURce {keyword}")

    def trigger(self, channel: int) -> None:
        """``TRIGger<n>`` - trigger a sweep or burst now (any trigger source)."""
        self._source(channel)
        self.write(f"TRIGger{channel}")

    # -- arbitrary waveforms ---------------------------------------------------

    def clear_volatile_memory(self, channel: int) -> None:
        """``[SOURce<n>:]DATA:VOLatile:CLEar`` - erase all arbs in volatile memory."""
        self.write(f"{self._source(channel)}:DATA:VOLatile:CLEar")

    def download_arbitrary(self, channel: int, name: str, values: Sequence[float]) -> None:
        """``[SOURce<n>:]DATA:ARBitrary <name>,<v1>,<v2>,...``.

        Values must already be normalized to -1.0 ... +1.0.
        """
        data = ",".join(f"{value:.6f}" for value in values)
        self.write(f"{self._source(channel)}:DATA:ARBitrary {name},{data}")

    def select_arbitrary(self, channel: int, name: str) -> None:
        """``[SOURce<n>:]FUNCtion:ARBitrary <name>`` - select the active arb."""
        self.write(f"{self._source(channel)}:FUNCtion:ARBitrary {name}")

    def set_arbitrary_sample_rate(self, channel: int, samples_per_second: float) -> None:
        """``[SOURce<n>:]FUNCtion:ARBitrary:SRATe <sample_rate>``."""
        self.write(f"{self._source(channel)}:FUNCtion:ARBitrary:SRATe {scpi_number(samples_per_second)}")

    def get_arbitrary_sample_rate(self, channel: int) -> float:
        """``[SOURce<n>:]FUNCtion:ARBitrary:SRATe?``."""
        return self.query_float(f"{self._source(channel)}:FUNCtion:ARBitrary:SRATe?", sim_value=40000.0)

    # -- output ---------------------------------------------------------------

    def set_output(self, channel: int, on: bool) -> None:
        """``OUTPut<n> {ON|OFF}``."""
        self._source(channel)  # validate channel number
        self.write(f"OUTPut{channel} {scpi_bool(on)}")

    def get_output(self, channel: int) -> bool:
        """``OUTPut<n>?``."""
        self._source(channel)
        return self.query_bool(f"OUTPut{channel}?")

    def set_output_load(self, channel: int, ohms: float | str) -> None:
        """``OUTPut<n>:LOAD {<ohms>|INFinity}`` - expected termination."""
        self._source(channel)
        if isinstance(ohms, str):
            keyword = ohms.strip().upper()
            if keyword not in {"INF", "INFINITY", "MIN", "MAX"}:
                msg = f"Invalid load {ohms!r}; use a resistance in Ohm or 'INFinity'"
                raise ValueError(msg)
            self.write(f"OUTPut{channel}:LOAD {keyword}")
        else:
            if not LOAD_MIN_OHMS <= ohms <= LOAD_MAX_OHMS:
                msg = f"Load must be {LOAD_MIN_OHMS:g}..{LOAD_MAX_OHMS:g} Ohm or 'INFinity', got {ohms:g}"
                raise ValueError(msg)
            self.write(f"OUTPut{channel}:LOAD {scpi_number(ohms)}")

    def get_output_load(self, channel: int) -> float:
        """``OUTPut<n>:LOAD?`` - high Z is reported as 9.9E+37."""
        self._source(channel)
        return self.query_float(f"OUTPut{channel}:LOAD?", sim_value=50.0)


class Keysight33500B(InstrumentApplication[Keysight33500BLowLevel]):
    """Application layer for the Keysight 33500B series waveform generator."""

    def __init__(self) -> None:
        super().__init__(Keysight33500BLowLevel())

    # -- standard waveforms -----------------------------------------------------

    def _configure_standard(
        self,
        function: str,
        channel: int,
        frequency: float | None = None,
        amplitude: float | None = None,
        offset: float | None = None,
    ) -> None:
        lowlevel = self._lowlevel
        lowlevel.set_function(channel, function)
        if frequency is not None:
            lowlevel.set_frequency(channel, frequency)
        if amplitude is not None:
            lowlevel.set_amplitude(channel, amplitude)
        if offset is not None:
            lowlevel.set_offset(channel, offset)

    def configure_sine(
        self,
        frequency: float | None = None,
        amplitude: float | None = None,
        offset: float | None = None,
        channel: int = 1,
    ) -> None:
        """Configure a sine wave (frequency in Hz, amplitude in Vpp, offset in V)."""
        self._configure_standard("SINusoid", channel, frequency, amplitude, offset)
        self.check_errors()

    def configure_square(
        self,
        frequency: float | None = None,
        amplitude: float | None = None,
        offset: float | None = None,
        duty_cycle: float | None = None,
        channel: int = 1,
    ) -> None:
        """Configure a square wave; ``duty_cycle`` in percent."""
        self._configure_standard("SQUare", channel, frequency, amplitude, offset)
        if duty_cycle is not None:
            self._lowlevel.set_square_duty_cycle(channel, duty_cycle)
        self.check_errors()

    def configure_ramp(
        self,
        frequency: float | None = None,
        amplitude: float | None = None,
        offset: float | None = None,
        symmetry: float | None = None,
        channel: int = 1,
    ) -> None:
        """Configure a ramp/triangle wave; ``symmetry`` in percent (50 = triangle)."""
        self._configure_standard("RAMP", channel, frequency, amplitude, offset)
        if symmetry is not None:
            self._lowlevel.set_ramp_symmetry(channel, symmetry)
        self.check_errors()

    def configure_pulse(
        self,
        frequency: float | None = None,
        amplitude: float | None = None,
        offset: float | None = None,
        width: float | None = None,
        duty_cycle: float | None = None,
        edge_time: float | None = None,
        channel: int = 1,
    ) -> None:
        """Configure a pulse wave; ``width``/``edge_time`` in seconds, ``duty_cycle`` in percent."""
        if width is not None and duty_cycle is not None:
            msg = "Give either width or duty_cycle, not both"
            raise ValueError(msg)
        self._configure_standard("PULSe", channel, frequency, amplitude, offset)
        if width is not None:
            self._lowlevel.set_pulse_width(channel, width)
        if duty_cycle is not None:
            self._lowlevel.set_pulse_duty_cycle(channel, duty_cycle)
        if edge_time is not None:
            self._lowlevel.set_pulse_edge_time(channel, edge_time)
        self.check_errors()

    def configure_noise(
        self,
        amplitude: float | None = None,
        offset: float | None = None,
        channel: int = 1,
    ) -> None:
        """Configure gaussian noise output."""
        self._configure_standard("NOISe", channel, None, amplitude, offset)
        self.check_errors()

    def configure_dc(self, offset: float, channel: int = 1) -> None:
        """Configure a DC level of ``offset`` Volts."""
        self._configure_standard("DC", channel, None, None, offset)
        self.check_errors()

    def set_phase(self, degrees: float, channel: int = 1) -> None:
        """Set the waveform phase offset in degrees (-360 ... +360).

        The offset is relative to the Sync output (and, on two channel
        models, to the other channel after ``PHASe:SYNChronize``).

        Raises:
            ValueError: If ``degrees`` is out of range.
        """
        if not PHASE_MIN_DEGREES <= degrees <= PHASE_MAX_DEGREES:
            msg = f"Phase must be {PHASE_MIN_DEGREES:g}..{PHASE_MAX_DEGREES:g} degrees, got {degrees:g}"
            raise ValueError(msg)
        self._lowlevel.write("UNIT:ANGLe DEGree")
        self._lowlevel.set_phase(channel, degrees)
        self.check_errors()

    def get_phase(self, channel: int = 1) -> float:
        """Return the waveform phase offset in degrees."""
        self._lowlevel.write("UNIT:ANGLe DEGree")
        return self._lowlevel.get_phase(channel)

    # -- sweep and burst -----------------------------------------------------------
    # The instrument allows only one of sweep, burst and modulation at a time;
    # enabling one switches the others off.

    def configure_sweep(
        self,
        start: float,
        stop: float,
        time: float,
        spacing: str = "linear",
        trigger_source: str = "immediate",
        channel: int = 1,
    ) -> None:
        """Sweep the frequency of the current waveform and enable the sweep.

        Args:
            start: Start frequency in Hz (``stop < start`` sweeps downwards).
            stop: Stop frequency in Hz.
            time: Sweep time in seconds.
            spacing: ``"linear"`` or ``"log"``.
            trigger_source: ``"immediate"`` (sweep repeats continuously),
                ``"external"``, ``"timer"`` or ``"bus"`` (see :meth:`trigger`).
            channel: Output channel (1 or 2).
        """
        lowlevel = self._lowlevel
        lowlevel.set_start_frequency(channel, start)
        lowlevel.set_stop_frequency(channel, stop)
        lowlevel.set_sweep_time(channel, time)
        lowlevel.set_sweep_spacing(channel, spacing)
        lowlevel.set_trigger_source(channel, trigger_source)
        lowlevel.set_sweep_state(channel, True)
        self.check_errors()

    def disable_sweep(self, channel: int = 1) -> None:
        """Switch the sweep off (the channel outputs the plain waveform again)."""
        self._lowlevel.set_sweep_state(channel, False)

    def configure_burst(
        self,
        cycles: int | str,
        period: float | None = None,
        trigger_source: str = "immediate",
        channel: int = 1,
    ) -> None:
        """Output bursts of ``cycles`` periods of the current waveform (triggered mode).

        Args:
            cycles: Periods per burst (>= 1), or ``"infinity"`` (runs until triggered).
            period: Burst repetition period in seconds; only used with
                ``trigger_source="immediate"``. ``None`` keeps the instrument setting.
            trigger_source: ``"immediate"`` (bursts repeat every ``period``),
                ``"external"``, ``"timer"`` or ``"bus"`` (see :meth:`trigger`).
            channel: Output channel (1 or 2).
        """
        lowlevel = self._lowlevel
        lowlevel.set_burst_mode(channel, "triggered")
        lowlevel.set_burst_cycles(channel, cycles)
        if period is not None:
            lowlevel.set_burst_period(channel, period)
        lowlevel.set_trigger_source(channel, trigger_source)
        lowlevel.set_burst_state(channel, True)
        self.check_errors()

    def disable_burst(self, channel: int = 1) -> None:
        """Switch burst mode off (the channel outputs the plain waveform again)."""
        self._lowlevel.set_burst_state(channel, False)

    def trigger(self, channel: int = 1) -> None:
        """Start one sweep or burst now, e.g. with ``trigger_source="bus"``."""
        self._lowlevel.trigger(channel)

    # -- arbitrary waveforms -------------------------------------------------------

    def load_arbitrary(
        self,
        values: Sequence[float],
        name: str = "MESSARB",
        sample_rate: float = 40000.0,
        amplitude: float | None = None,
        offset: float | None = None,
        channel: int = 1,
        normalize: bool = True,
        clear_volatile: bool = True,
        activate: bool = True,
    ) -> None:
        """Download an arbitrary waveform into volatile memory.

        Args:
            values: Waveform samples. The instrument expects -1.0 ... +1.0;
                with ``normalize=True`` (default) the data is scaled so the
                largest magnitude becomes 1.0.
            name: Arb name on the instrument (letter followed by up to 11
                letters/digits/underscores).
            sample_rate: Playback rate in Sa/s (1 uSa/s ... 250 MSa/s).
            amplitude: Output amplitude in Vpp mapped onto -1..+1 (optional).
            offset: Output offset in Volts (optional).
            channel: Output channel (1 or 2).
            normalize: Scale values to full range. If False, values outside
                -1..+1 raise a ValueError.
            clear_volatile: Clear volatile arb memory first (the instrument
                refuses duplicate names otherwise). Note: this erases *all*
                unsaved arbs of that channel.
            activate: Select the arb and switch the channel to ARB mode.

        Raises:
            ValueError: If the name or the data is invalid.
            InstrumentCommandError: If the instrument rejects the download.
        """
        if _ARB_NAME_RE.fullmatch(name) is None:
            msg = f"Invalid arb name {name!r} (letter followed by up to 11 letters/digits/underscores)"
            raise ValueError(msg)
        if not ARB_MIN_POINTS <= len(values) <= ARB_MAX_POINTS:
            msg = f"Arb length must be {ARB_MIN_POINTS}..{ARB_MAX_POINTS} points, got {len(values)}"
            raise ValueError(msg)
        data = [float(value) for value in values]
        peak = max(abs(value) for value in data)
        if normalize:
            if peak == 0.0:
                msg = "Cannot normalize an all-zero waveform"
                raise ValueError(msg)
            data = [value / peak for value in data]
        elif peak > 1.0:
            msg = f"Arb values must be within -1.0..+1.0 (peak is {peak:g}); use normalize=True"
            raise ValueError(msg)

        lowlevel = self._lowlevel
        if clear_volatile:
            lowlevel.clear_volatile_memory(channel)
        with lowlevel.temporary_timeout(60000.0):
            lowlevel.download_arbitrary(channel, name, data)
            lowlevel.wait_for_operation_complete()
        if activate:
            lowlevel.select_arbitrary(channel, name)
            lowlevel.set_arbitrary_sample_rate(channel, sample_rate)
            if amplitude is not None:
                lowlevel.set_amplitude(channel, amplitude)
            if offset is not None:
                lowlevel.set_offset(channel, offset)
            lowlevel.set_function(channel, "ARB")
        self.check_errors()

    def load_arbitrary_csv(
        self,
        path: str | Path,
        name: str | None = None,
        sample_rate: float = 40000.0,
        amplitude: float | None = None,
        offset: float | None = None,
        channel: int = 1,
        normalize: bool = True,
        clear_volatile: bool = True,
        activate: bool = True,
    ) -> None:
        """Load an arbitrary waveform from a CSV/text file.

        The file may contain one sample per line or comma/semicolon separated
        values; ``#`` comment lines and a single header line are skipped.
        ``name`` defaults to the file stem (sanitized). See
        :meth:`load_arbitrary` for the remaining arguments.
        """
        file_path = Path(path)
        values = _read_waveform_file(file_path)
        if name is None:
            stem = re.sub(r"[^A-Za-z0-9_]", "_", file_path.stem)[:12] or "MESSARB"
            name = stem if stem[0].isalpha() else f"A{stem}"[:12]
        self.load_arbitrary(
            values,
            name=name,
            sample_rate=sample_rate,
            amplitude=amplitude,
            offset=offset,
            channel=channel,
            normalize=normalize,
            clear_volatile=clear_volatile,
            activate=activate,
        )

    # -- output --------------------------------------------------------------------

    def output(self, on: bool, channel: int = 1) -> None:
        """Switch the channel output on/off."""
        self._lowlevel.set_output(channel, on)

    def set_output_load(self, load: float | str = 50, channel: int = 1) -> None:
        """Set the expected output termination: ``50`` (default) or ``"highz"``.

        The generator always has a fixed 50 Ohm source impedance; this only
        tells it which load to expect, so the programmed amplitude/offset
        appear at the load. Set ``50`` for a 50 Ohm terminated cable and
        ``"highz"`` (also ``"INFinity"``) for a scope/high impedance input -
        a mismatch gives double or half the expected voltage. Any value
        from 1 to 10 000 Ohm is accepted, too.

        Raises:
            ValueError: If ``load`` is neither a valid resistance nor high Z.
        """
        if isinstance(load, str):
            if load.strip().upper() not in _HIGH_Z_KEYWORDS:
                msg = f"Invalid load {load!r}; use a resistance in Ohm (e.g. 50) or 'highz'"
                raise ValueError(msg)
            load = "INFinity"
        self._lowlevel.set_output_load(channel, load)
        self.check_errors()

    def get_output_load(self, channel: int = 1) -> float:
        """Return the expected output termination in Ohm (``math.inf`` for high Z)."""
        ohms = self._lowlevel.get_output_load(channel)
        return math.inf if ohms >= _LOAD_INFINITE_THRESHOLD else ohms


def _keyword(value: str, keywords: dict[str, str], what: str) -> str:
    """Map a user spelling (case insensitive) to its SCPI keyword."""
    keyword = keywords.get(value.strip().upper())
    if keyword is None:
        allowed = ", ".join(sorted({name.lower() for name in keywords.values()}))
        msg = f"Invalid {what} {value!r}; allowed: {allowed}"
        raise ValueError(msg)
    return keyword


def _read_waveform_file(path: Path) -> list[float]:
    """Read waveform samples from a text/CSV file."""
    if not path.is_file():
        msg = f"Waveform file not found: {path}"
        raise FileNotFoundError(msg)
    values: list[float] = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = [token for token in re.split(r"[,;\s]+", line) if token]
        try:
            values.extend(float(token) for token in tokens)
        except ValueError:
            if line_number == 1 or (not values and line_number <= 2):
                continue  # tolerate a header line
            msg = f"Non-numeric value in {path} line {line_number}: {raw_line!r}"
            raise ValueError(msg) from None
    if not values:
        msg = f"No waveform samples found in {path}"
        raise ValueError(msg)
    return values
