"""Driver for the TTi (Aim-TTi) PL303QMD-P dual output DC power supply.

The PL series uses a simple, non-SCPI command set (``V1 5.0``, ``OP1 1``, ...).
Channel numbering follows the instrument: output 1 is the Master (right hand)
output, output 2 the Slave. Both outputs deliver 0-30 V / 0-3 A.

Usage::

    from messknecht import TTiPL303QMD

    with TTiPL303QMD() as psu:
        psu.initialize("USB0::0x103E::...::INSTR", reset=True)
        psu.ch1.configure(voltage=5.0, current_limit=0.5)
        psu.ch1.output = True
        print(psu.ch1.measured_voltage)
"""

from __future__ import annotations

import enum

from messknecht.core.exceptions import InstrumentCommandError
from messknecht.core.instrument import InstrumentApplication, VisaInstrument
from messknecht.core.scpi import scpi_number
from messknecht.core.simulation import SimulationBackend

#: Execution Error Register codes (manual, section "Status Reporting").
EXECUTION_ERRORS = {
    100: "Range error: the numeric value sent is not allowed",
    101: "Recall of set up data: store contains corrupted data",
    102: "Recall of set up data: store contains no data",
    103: "Second output not available (single channel or parallel mode)",
    104: "Command not valid with output on (e.g. IRANGE)",
    200: "Read only: interface has no write privileges (interface lock)",
}


class CurrentRange(enum.IntEnum):
    """Current meter/setting range of an output (``IRANGE``)."""

    LOW = 1  #: 500 mA range (0.1 mA meter, 0.01 mA setting resolution)
    HIGH = 2  #: 3 A range


class _TTiPL303QMDSimulation(SimulationBackend):
    """Generic simulation stub: only overrides ``*IDN?`` for this model.

    Writes are logged and ignored; numeric reads fall back to the typed-query
    defaults. Setpoint round-trip is not simulated.
    """

    IDN = "THURLBY THANDAR,PL303QMD-P,0,1.00-1.00"


class TTiPL303QMDLowLevel(VisaInstrument):
    """Low level wrapper around the PL303QMD remote command set."""

    SIMULATION_BACKEND = _TTiPL303QMDSimulation
    #: Responses are terminated with CR LF; commands with LF.
    READ_TERMINATION = "\n"
    WRITE_TERMINATION = "\n"

    # -- settings ----------------------------------------------------------

    def set_voltage(self, channel: int, volts: float) -> None:
        """``V<n> <nrf>`` - set the output voltage."""
        self.write(f"V{channel} {scpi_number(volts)}")

    def get_voltage(self, channel: int) -> float:
        """``V<n>?`` - return the voltage *setting* (response ``V<n> <nr2>``)."""
        return self.query_last_float(f"V{channel}?")

    def set_current_limit(self, channel: int, amps: float) -> None:
        """``I<n> <nrf>`` - set the current limit."""
        self.write(f"I{channel} {scpi_number(amps)}")

    def get_current_limit(self, channel: int) -> float:
        """``I<n>?`` - return the current limit setting (response ``I<n> <nr2>``)."""
        return self.query_last_float(f"I{channel}?")

    def set_over_voltage_protection(self, channel: int, volts: float) -> None:
        """``OVP<n> <nrf>`` - set the over voltage protection trip point."""
        self.write(f"OVP{channel} {scpi_number(volts)}")

    def get_over_voltage_protection(self, channel: int) -> float:
        """``OVP<n>?`` - return the OVP trip point (response ``VP<n> <nr2>``)."""
        return self.query_last_float(f"OVP{channel}?")

    def set_over_current_protection(self, channel: int, amps: float) -> None:
        """``OCP<n> <nrf>`` - set the over current protection trip point."""
        self.write(f"OCP{channel} {scpi_number(amps)}")

    def get_over_current_protection(self, channel: int) -> float:
        """``OCP<n>?`` - return the OCP trip point (response ``CP<n> <nr2>``)."""
        return self.query_last_float(f"OCP{channel}?")

    def set_current_range(self, channel: int, current_range: CurrentRange) -> None:
        """``IRANGE<n> <nrf>`` - 1 = low (500 mA), 2 = high. Output must be off."""
        self.write(f"IRANGE{channel} {int(current_range)}")

    def get_current_range(self, channel: int) -> CurrentRange:
        """``IRANGE<n>?`` - return the current range."""
        return CurrentRange(self.query_int(f"IRANGE{channel}?", sim_value=int(CurrentRange.HIGH)))

    # -- readback ----------------------------------------------------------

    def measure_voltage(self, channel: int) -> float:
        """``V<n>O?`` - return the readback (measured) output voltage in Volts."""
        return self.query_last_float(f"V{channel}O?")

    def measure_current(self, channel: int) -> float:
        """``I<n>O?`` - return the readback (measured) output current in Amps."""
        return self.query_last_float(f"I{channel}O?")

    # -- output state ------------------------------------------------------

    def set_output(self, channel: int, on: bool) -> None:
        """``OP<n> <nrf>`` - switch output <n> on/off."""
        self.write(f"OP{channel} {1 if on else 0}")

    def get_output(self, channel: int) -> bool:
        """``OP<n>?`` - return the on/off state of output <n>."""
        return self.query_bool(f"OP{channel}?")

    def set_output_all(self, on: bool) -> None:
        """``OPALL <nrf>`` - switch all outputs on/off simultaneously."""
        self.write(f"OPALL {1 if on else 0}")

    # -- misc ---------------------------------------------------------------

    def trip_reset(self) -> None:
        """``TRIPRST`` - attempt to clear all trip conditions."""
        self.write("TRIPRST")

    def local(self) -> None:
        """``LOCAL`` - return the instrument to local (front panel) control."""
        self.write("LOCAL")

    def get_config(self) -> int:
        """``CONFIG?`` - operating mode: 0 tracking, 1 single/parallel, 2 dual."""
        return self.query_int("CONFIG?", sim_value=2)

    def get_execution_error(self) -> int:
        """``EER?`` - query and clear the Execution Error Register."""
        return self.query_int("EER?", sim_value=0)

    def get_query_error(self) -> int:
        """``QER?`` - query and clear the Query Error Register."""
        return self.query_int("QER?", sim_value=0)

    def check_errors(self) -> None:
        """Check the Execution Error Register and raise if it is non-zero.

        The PL series does not implement ``SYSTem:ERRor?``; errors are
        reported through the Execution Error Register instead.
        """
        code = self.get_execution_error()
        if code != 0:
            description = EXECUTION_ERRORS.get(code, "Unknown execution error")
            msg = f"Power supply reported execution error {code}: {description}"
            raise InstrumentCommandError(msg, errors=[str(code)])


class TTiPL303QMDChannel:
    """One output of the power supply, exposed through properties.

    All setpoint properties read back from the instrument, they do not cache
    anything locally.
    """

    def __init__(self, lowlevel: TTiPL303QMDLowLevel, number: int) -> None:
        self._lowlevel = lowlevel
        self._number = number

    @property
    def number(self) -> int:
        """The output number on the instrument (1 = Master, 2 = Slave)."""
        return self._number

    @property
    def voltage(self) -> float:
        """Output voltage setpoint in Volts."""
        return self._lowlevel.get_voltage(self._number)

    @voltage.setter
    def voltage(self, volts: float) -> None:
        self._lowlevel.set_voltage(self._number, volts)

    @property
    def current_limit(self) -> float:
        """Current limit setpoint in Amps."""
        return self._lowlevel.get_current_limit(self._number)

    @current_limit.setter
    def current_limit(self, amps: float) -> None:
        self._lowlevel.set_current_limit(self._number, amps)

    @property
    def measured_voltage(self) -> float:
        """Measured (readback) output voltage in Volts."""
        return self._lowlevel.measure_voltage(self._number)

    @property
    def measured_current(self) -> float:
        """Measured (readback) output current in Amps."""
        return self._lowlevel.measure_current(self._number)

    @property
    def output(self) -> bool:
        """Output on/off state."""
        return self._lowlevel.get_output(self._number)

    @output.setter
    def output(self, on: bool) -> None:
        self._lowlevel.set_output(self._number, on)

    @property
    def ovp(self) -> float:
        """Over voltage protection trip point in Volts."""
        return self._lowlevel.get_over_voltage_protection(self._number)

    @ovp.setter
    def ovp(self, volts: float) -> None:
        self._lowlevel.set_over_voltage_protection(self._number, volts)

    @property
    def ocp(self) -> float:
        """Over current protection trip point in Amps."""
        return self._lowlevel.get_over_current_protection(self._number)

    @ocp.setter
    def ocp(self, amps: float) -> None:
        self._lowlevel.set_over_current_protection(self._number, amps)

    @property
    def current_range(self) -> CurrentRange:
        """Current range (LOW = 500 mA, HIGH = 3 A). Output must be off to change it."""
        return self._lowlevel.get_current_range(self._number)

    @current_range.setter
    def current_range(self, current_range: CurrentRange) -> None:
        self._lowlevel.set_current_range(self._number, CurrentRange(current_range))

    def configure(
        self,
        voltage: float | None = None,
        current_limit: float | None = None,
        ovp: float | None = None,
        ocp: float | None = None,
        output: bool | None = None,
    ) -> None:
        """Set the given parameters of this output in one call.

        Only parameters that are not ``None`` are written. The instrument
        error register is checked once at the end.
        """
        if ovp is not None:
            self._lowlevel.set_over_voltage_protection(self._number, ovp)
        if ocp is not None:
            self._lowlevel.set_over_current_protection(self._number, ocp)
        if voltage is not None:
            self._lowlevel.set_voltage(self._number, voltage)
        if current_limit is not None:
            self._lowlevel.set_current_limit(self._number, current_limit)
        if output is not None:
            self._lowlevel.set_output(self._number, output)
        self._lowlevel.check_errors()


class TTiPL303QMD(InstrumentApplication[TTiPL303QMDLowLevel]):
    """Application layer for the TTi PL303QMD-P dual output power supply."""

    CHANNEL_COUNT = 2

    def __init__(self) -> None:
        super().__init__(TTiPL303QMDLowLevel())
        self._channels = tuple(
            TTiPL303QMDChannel(self._lowlevel, number) for number in range(1, self.CHANNEL_COUNT + 1)
        )

    # -- channel access ------------------------------------------------------

    @property
    def channels(self) -> tuple[TTiPL303QMDChannel, ...]:
        """All outputs of the supply, in order (index 0 = output 1)."""
        return self._channels

    def channel(self, number: int) -> TTiPL303QMDChannel:
        """Return the channel object for output ``number`` (1-based)."""
        if not 1 <= number <= self.CHANNEL_COUNT:
            msg = f"Channel must be 1..{self.CHANNEL_COUNT}, got {number}"
            raise ValueError(msg)
        return self._channels[number - 1]

    @property
    def ch1(self) -> TTiPL303QMDChannel:
        """Output 1 (Master, right hand output)."""
        return self._channels[0]

    @property
    def ch2(self) -> TTiPL303QMDChannel:
        """Output 2 (Slave)."""
        return self._channels[1]

    # -- convenience ----------------------------------------------------------

    def configure(
        self,
        channel: int = 1,
        voltage: float | None = None,
        current_limit: float | None = None,
        ovp: float | None = None,
        ocp: float | None = None,
        output: bool | None = None,
    ) -> None:
        """Configure one output; see :meth:`TTiPL303QMDChannel.configure`."""
        self.channel(channel).configure(voltage=voltage, current_limit=current_limit, ovp=ovp, ocp=ocp, output=output)

    def output_all(self, on: bool) -> None:
        """Switch all outputs on/off simultaneously (``OPALL``)."""
        self._lowlevel.set_output_all(on)

    def trip_reset(self) -> None:
        """Attempt to clear all trip conditions (``TRIPRST``)."""
        self._lowlevel.trip_reset()

    def local(self) -> None:
        """Return the instrument to front panel control (``LOCAL``)."""
        self._lowlevel.local()
