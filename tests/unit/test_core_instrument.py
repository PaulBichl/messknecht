from __future__ import annotations

from typing import cast

import pytest
import pyvisa

from messknecht.core.exceptions import (
    InstrumentCommandError,
    InstrumentDataError,
    InstrumentIOError,
    InstrumentTimeoutError,
    NotInitializedError,
    OptionStringError,
    SimulationError,
)
from messknecht.core.instrument import VisaInstrument
from messknecht.core.simulation import SimulationBackend


@pytest.fixture
def sim_instrument() -> VisaInstrument:
    instrument = VisaInstrument()
    instrument.initialize("SIM::generic", True, "simulate=true")
    return instrument


def test_initialize_simulated(sim_instrument: VisaInstrument) -> None:
    assert sim_instrument.is_initialized
    assert sim_instrument.is_simulated
    assert sim_instrument.resource_name == "SIM::generic"
    assert "Messknecht" in sim_instrument.idn


def test_reset_traffic_is_logged(sim_instrument: VisaInstrument) -> None:
    simulation = sim_instrument.simulation
    assert simulation is not None
    assert "*RST" in simulation.log
    assert "*CLS" in simulation.log


def test_unhandled_plain_query_raises_simulation_error(sim_instrument: VisaInstrument) -> None:
    with pytest.raises(SimulationError, match="not supported in simulation"):
        sim_instrument.query(":SOME:OBSCURE:QUERY?")


def test_typed_queries_fall_back_to_defaults(sim_instrument: VisaInstrument) -> None:
    value = sim_instrument.query_float(":VOLT?", sim_value=2.0)
    assert value == pytest.approx(2.0, abs=0.1)
    assert sim_instrument.query_int(":COUNT?", sim_value=7) == 7
    assert sim_instrument.query_bool(":STATE?", sim_value=True) is True
    assert sim_instrument.query_last_float("V1?", sim_value=3.3) == pytest.approx(3.3, abs=0.1)


def test_check_errors_passes_with_empty_queue(sim_instrument: VisaInstrument) -> None:
    sim_instrument.check_errors()


def test_close_and_not_initialized_error(sim_instrument: VisaInstrument) -> None:
    sim_instrument.close()
    assert not sim_instrument.is_initialized
    with pytest.raises(NotInitializedError, match="initialize"):
        sim_instrument.write("*CLS")


def test_context_manager_closes() -> None:
    with VisaInstrument() as instrument:
        instrument.initialize("SIM::generic", False, "simulate=true")
        assert instrument.is_initialized
    assert not instrument.is_initialized


def test_reinitialize_is_allowed(sim_instrument: VisaInstrument) -> None:
    sim_instrument.initialize("SIM::other", False, "simulate=true")
    assert sim_instrument.resource_name == "SIM::other"


def test_invalid_option_string_raises() -> None:
    instrument = VisaInstrument()
    with pytest.raises(OptionStringError, match="key=value"):
        instrument.initialize("SIM::generic", False, "simulate")


def test_options_are_exposed(sim_instrument: VisaInstrument) -> None:
    assert sim_instrument.options == {"simulate": "true"}


def test_temporary_timeout_is_noop_in_simulation(sim_instrument: VisaInstrument) -> None:
    with sim_instrument.temporary_timeout(60000.0):
        assert sim_instrument.query("*OPC?") == "1"


class _BadResponseBackend(SimulationBackend):
    """Answers every driver specific query with text that is not a number."""

    def handle_query(self, command: str) -> str:
        return "NOT A NUMBER"


class _ErrorQueueBackend(SimulationBackend):
    """Reports two queued errors, then an empty queue."""

    def reset(self) -> None:
        super().reset()
        self.state["errors"] = ['-113,"Undefined header"', '-222,"Data out of range"']

    def query(self, command: str) -> str | None:
        if command.strip().upper().lstrip(":").startswith("SYST"):
            queued = cast("list[str]", self.state["errors"])
            return queued.pop(0) if queued else '+0,"No error"'
        return super().query(command)


def _instrument_with(backend: type[SimulationBackend]) -> VisaInstrument:
    class _Instrument(VisaInstrument):
        SIMULATION_BACKEND = backend

    instrument = _Instrument()
    instrument.initialize("SIM::generic", True, "simulate=true")
    return instrument


def test_check_errors_raises_and_drains_the_queue() -> None:
    instrument = _instrument_with(_ErrorQueueBackend)
    with pytest.raises(InstrumentCommandError, match="Undefined header") as excinfo:
        instrument.check_errors()
    assert len(excinfo.value.errors) == 2
    instrument.check_errors()  # queue is empty now


def test_unparsable_numeric_responses_raise_data_errors() -> None:
    instrument = _instrument_with(_BadResponseBackend)
    with pytest.raises(InstrumentDataError, match="Expected a number"):
        instrument.query_float(":VOLT?")
    with pytest.raises(InstrumentDataError, match="Expected an integer"):
        instrument.query_int(":COUNT?")
    with pytest.raises(InstrumentDataError, match="parse"):
        instrument.query_last_float(":VOLT?")
    with pytest.raises(InstrumentDataError, match="boolean"):
        instrument.query_bool(":STATE?")


def test_visa_timeout_is_translated(sim_instrument: VisaInstrument) -> None:
    timeout = pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_timeout)
    with (
        pytest.raises(InstrumentTimeoutError, match="Timeout while reading"),
        sim_instrument._translate_visa_errors("reading"),
    ):
        raise timeout


def test_other_visa_errors_become_io_errors(sim_instrument: VisaInstrument) -> None:
    failure = pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_system_error)
    with (
        pytest.raises(InstrumentIOError, match="VISA error while writing"),
        sim_instrument._translate_visa_errors("writing"),
    ):
        raise failure


def test_binary_query_unsupported_in_simulation(sim_instrument: VisaInstrument) -> None:
    with pytest.raises(SimulationError, match="not supported in simulation"):
        sim_instrument.query_binary_block(":DATA?")
