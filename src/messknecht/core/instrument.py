"""Generic VISA instrument base class and the application layer base.

Architecture (see ``docs/developer-guide.md``):

* :class:`VisaInstrument` is the *low level* base class. Concrete low level
  drivers subclass it and wrap their instrument's SCPI commands in thin,
  typed methods. It owns the pyvisa session (or the simulation session) and
  provides typed read/write/query helpers plus error-queue checking.
* :class:`InstrumentApplication` is the base for the *application layer*. An
  application driver owns exactly one low level driver (``self._lowlevel``)
  and composes its methods into user friendly functionality.
"""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, ClassVar, Self, cast

import pyvisa
import pyvisa.constants
from pyvisa.resources import MessageBasedResource

from messknecht.core.exceptions import (
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDataError,
    InstrumentIOError,
    InstrumentTimeoutError,
    NotInitializedError,
    SimulationError,
)
from messknecht.core.options import option_as_bool, option_as_float, parse_option_string
from messknecht.core.scpi import parse_last_float, parse_leading_error_code, parse_scpi_bool
from messknecht.core.simulation import SimulatedSession, SimulationBackend, sim_float

if TYPE_CHECKING:
    from collections.abc import Iterator

_MAX_ERROR_QUEUE_READS = 50

_resource_managers: dict[str, pyvisa.ResourceManager] = {}
_resource_managers_lock = threading.Lock()


def _get_resource_manager(visa_library: str) -> pyvisa.ResourceManager:
    """Return a cached ResourceManager (one per VISA backend string)."""
    with _resource_managers_lock:
        if visa_library not in _resource_managers:
            _resource_managers[visa_library] = pyvisa.ResourceManager(visa_library)
        return _resource_managers[visa_library]


class VisaInstrument:
    """Generic message based VISA instrument (low level driver base class).

    Lifecycle::

        instr = SomeLowLevelDriver()
        instr.initialize("TCPIP0::192.168.1.5::INSTR", reset=True)
        ...
        instr.close()

    ``initialize()`` accepts an option string of ``key=value`` pairs (see
    :mod:`messknecht.core.options`), e.g. ``"simulate=true"`` runs the driver
    against its :class:`~messknecht.core.simulation.SimulationBackend`.
    """

    #: VISA write termination character(s); ``None`` keeps the pyvisa default.
    WRITE_TERMINATION: ClassVar[str | None] = "\n"
    #: VISA read termination character(s); ``None`` keeps the pyvisa default.
    READ_TERMINATION: ClassVar[str | None] = "\n"
    #: Default VISA I/O timeout in milliseconds (option ``timeout`` overrides).
    DEFAULT_TIMEOUT_MS: ClassVar[float] = 5000.0
    #: Simulation backend class used when ``simulate=true``.
    SIMULATION_BACKEND: ClassVar[type[SimulationBackend]] = SimulationBackend

    def __init__(self) -> None:
        self._resource: MessageBasedResource | None = None
        self._simulation: SimulatedSession | None = None
        self._options: dict[str, str] = {}
        self._resource_name = ""
        self._auto_error_check = False

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def initialize(self, res: str, reset: bool, option_string: str = "") -> None:
        """Open the connection to the instrument.

        Args:
            res: VISA resource string, e.g. ``"USB0::0x0957::...::INSTR"``.
            reset: Reset the instrument (``*RST``) after connecting.
            option_string: ``key=value`` pairs, e.g. ``"simulate=true, timeout=10000"``.
                See :mod:`messknecht.core.options` for the well-known keys.

        Raises:
            OptionStringError: If the option string is malformed.
            InstrumentConnectionError: If the VISA session cannot be opened.
        """
        if self.is_initialized:
            self.close()
        self._options = parse_option_string(option_string)
        self._resource_name = res
        self._auto_error_check = option_as_bool(self._options, "error_check", default=False)
        timeout_ms = option_as_float(self._options, "timeout", default=self.DEFAULT_TIMEOUT_MS)

        if option_as_bool(self._options, "simulate", default=False):
            self._simulation = SimulatedSession(self.SIMULATION_BACKEND())
            self._simulation.timeout_ms = timeout_ms
        else:
            self._resource = self._open_resource(res, timeout_ms)

        if reset:
            self.reset()
        self._configure_defaults()

    def _open_resource(self, res: str, timeout_ms: float) -> MessageBasedResource:
        visa_library = self._options.get("visa_library", "")
        try:
            manager = _get_resource_manager(visa_library)
            resource = manager.open_resource(res)
        except (pyvisa.Error, OSError, ValueError) as exc:
            msg = f"Could not open VISA resource {res!r}: {exc}"
            raise InstrumentConnectionError(msg) from exc
        if not isinstance(resource, MessageBasedResource):
            resource.close()
            msg = f"Resource {res!r} is not a message based instrument"
            raise InstrumentConnectionError(msg)
        resource.timeout = timeout_ms
        if self.WRITE_TERMINATION is not None:
            resource.write_termination = self.WRITE_TERMINATION
        if self.READ_TERMINATION is not None:
            resource.read_termination = self.READ_TERMINATION
        return resource

    def _configure_defaults(self) -> None:
        """Hook for subclasses: called at the end of ``initialize()``."""

    def close(self) -> None:
        """Close the VISA session. Safe to call multiple times."""
        if self._resource is not None:
            with contextlib.suppress(pyvisa.Error):
                self._resource.close()
            self._resource = None
        self._simulation = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # State                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_initialized(self) -> bool:
        """True after a successful ``initialize()`` (real or simulated)."""
        return self._resource is not None or self._simulation is not None

    @property
    def is_simulated(self) -> bool:
        """True when running against the simulation backend."""
        return self._simulation is not None

    @property
    def simulation(self) -> SimulatedSession | None:
        """The simulation session (command log etc.), or ``None`` if real."""
        return self._simulation

    @property
    def resource_name(self) -> str:
        """The VISA resource string passed to ``initialize()``."""
        return self._resource_name

    @property
    def options(self) -> dict[str, str]:
        """The parsed option string (lower-case keys)."""
        return dict(self._options)

    @property
    def idn(self) -> str:
        """The instrument identification (``*IDN?``)."""
        return self.query("*IDN?")

    def _require_resource(self) -> MessageBasedResource:
        if self._resource is None:
            msg = "Instrument is not initialized (call initialize() first)"
            raise NotInitializedError(msg)
        return self._resource

    @contextlib.contextmanager
    def _translate_visa_errors(self, action: str) -> Iterator[None]:
        try:
            yield
        except pyvisa.errors.VisaIOError as exc:
            if exc.error_code == pyvisa.constants.StatusCode.error_timeout:
                msg = f"Timeout while {action} ({self._resource_name})"
                raise InstrumentTimeoutError(msg) from exc
            msg = f"VISA error while {action} ({self._resource_name}): {exc}"
            raise InstrumentIOError(msg) from exc
        except pyvisa.Error as exc:
            msg = f"VISA error while {action} ({self._resource_name}): {exc}"
            raise InstrumentIOError(msg) from exc

    @contextlib.contextmanager
    def temporary_timeout(self, timeout_ms: float) -> Iterator[None]:
        """Temporarily raise the VISA timeout (e.g. for big data transfers)."""
        if self._simulation is not None or self._resource is None:
            yield
            return
        previous = self._resource.timeout
        self._resource.timeout = timeout_ms
        try:
            yield
        finally:
            self._resource.timeout = previous

    # ------------------------------------------------------------------ #
    # Raw I/O                                                            #
    # ------------------------------------------------------------------ #

    def write(self, command: str) -> None:
        """Send a command to the instrument."""
        if self._simulation is not None:
            self._simulation.write(command)
        else:
            with self._translate_visa_errors(f"writing {command!r}"):
                self._require_resource().write(command)
        if self._auto_error_check:
            self.check_errors()

    def query(self, command: str) -> str:
        """Send a query and return the stripped response string.

        In simulation mode, raises
        :class:`~messknecht.core.exceptions.SimulationError` if the backend
        has no canned response for this query. Use the typed helpers
        (``query_float`` etc.) where a generic simulated value is acceptable.
        """
        if self._simulation is not None:
            response = self._simulation.query(command)
            if response is None:
                msg = f"Query {command!r} is not supported in simulation mode"
                raise SimulationError(msg)
            return response
        with self._translate_visa_errors(f"querying {command!r}"):
            return self._require_resource().query(command).strip()

    def _query_simulated(self, command: str) -> str | None:
        assert self._simulation is not None
        return self._simulation.query(command)

    def query_float(self, command: str, sim_value: float = 1.0) -> float:
        """Query a float. In simulation, unhandled queries return ``sim_value`` + noise."""
        if self._simulation is not None:
            response = self._query_simulated(command)
            if response is None:
                return sim_float(sim_value)
        else:
            response = self.query(command)
        try:
            return float(response)
        except ValueError as exc:
            msg = f"Expected a number as response to {command!r}, got {response!r}"
            raise InstrumentDataError(msg) from exc

    def query_last_float(self, command: str, sim_value: float = 1.0) -> float:
        """Query a float that may be embedded in text and return the last number.

        Handles responses that echo the command or append a unit, e.g. the TTi
        PL303QMD answers ``V1?`` with ``"V1 5.000"``. In simulation, unhandled
        queries return ``sim_value`` + noise (like :meth:`query_float`).
        """
        if self._simulation is not None:
            response = self._query_simulated(command)
            if response is None:
                return sim_float(sim_value)
        else:
            response = self.query(command)
        return parse_last_float(response)

    def query_int(self, command: str, sim_value: int = 0) -> int:
        """Query an integer. In simulation, unhandled queries return ``sim_value``."""
        if self._simulation is not None:
            response = self._query_simulated(command)
            if response is None:
                return sim_value
        else:
            response = self.query(command)
        try:
            return int(float(response))
        except ValueError as exc:
            msg = f"Expected an integer as response to {command!r}, got {response!r}"
            raise InstrumentDataError(msg) from exc

    def query_bool(self, command: str, sim_value: bool = False) -> bool:
        """Query a boolean (0/1/ON/OFF). In simulation, unhandled queries return ``sim_value``."""
        if self._simulation is not None:
            response = self._query_simulated(command)
            if response is None:
                return sim_value
        else:
            response = self.query(command)
        return parse_scpi_bool(response)

    def query_binary_block(self, command: str) -> bytes:
        """Query an IEEE-488.2 definite length binary block and return its payload."""
        if self._simulation is not None:
            data = self._simulation.query_binary(command)
            if data is None:
                msg = f"Binary query {command!r} is not supported in simulation mode"
                raise SimulationError(msg)
            return data
        with self._translate_visa_errors(f"querying binary block {command!r}"):
            payload = self._require_resource().query_binary_values(command, datatype="B", container=bytearray)
        return bytes(cast("bytearray", payload))

    # ------------------------------------------------------------------ #
    # Common commands                                                    #
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Reset the instrument (``*CLS``, ``*RST``) and wait for completion."""
        self.write("*CLS")
        self.write("*RST")
        with self.temporary_timeout(max(10000.0, self.DEFAULT_TIMEOUT_MS)):
            self.query("*OPC?")

    def wait_for_operation_complete(self, timeout_ms: float | None = None) -> None:
        """Block until all pending operations finished (``*OPC?``)."""
        if timeout_ms is None:
            self.query("*OPC?")
            return
        with self.temporary_timeout(timeout_ms):
            self.query("*OPC?")

    def check_errors(self) -> None:
        """Read the instrument error queue and raise if it is not empty.

        The default implementation drains the SCPI standard ``SYSTem:ERRor?``
        queue. Drivers for non-SCPI instruments override this.

        Raises:
            InstrumentCommandError: If the instrument reported errors.
        """
        errors: list[str] = []
        for _ in range(_MAX_ERROR_QUEUE_READS):
            response = self.query("SYSTem:ERRor?")
            if parse_leading_error_code(response) == 0:
                break
            errors.append(response)
        if errors:
            msg = f"Instrument reported errors: {'; '.join(errors)}"
            raise InstrumentCommandError(msg, errors=errors)


class InstrumentApplication[TLowLevel: VisaInstrument]:
    """Base class for application layer drivers.

    An application driver owns one low level driver instance and exposes user
    friendly, composed operations. The low level driver stays accessible via
    :attr:`lowlevel` for anything the application layer does not cover.
    """

    def __init__(self, lowlevel: TLowLevel) -> None:
        self._lowlevel: TLowLevel = lowlevel

    @property
    def lowlevel(self) -> TLowLevel:
        """The low level (SCPI wrapper) driver."""
        return self._lowlevel

    def initialize(self, res: str, reset: bool, option_string: str = "") -> None:
        """Open the connection. See :meth:`VisaInstrument.initialize`."""
        self._lowlevel.initialize(res, reset, option_string)

    def close(self) -> None:
        """Close the connection. Safe to call multiple times."""
        self._lowlevel.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def is_initialized(self) -> bool:
        """True after a successful ``initialize()``."""
        return self._lowlevel.is_initialized

    @property
    def is_simulated(self) -> bool:
        """True when running against the simulation backend."""
        return self._lowlevel.is_simulated

    @property
    def idn(self) -> str:
        """The instrument identification (``*IDN?``)."""
        return self._lowlevel.idn

    def reset(self) -> None:
        """Reset the instrument and wait for completion."""
        self._lowlevel.reset()

    def check_errors(self) -> None:
        """Read the instrument error queue and raise if it is not empty."""
        self._lowlevel.check_errors()
