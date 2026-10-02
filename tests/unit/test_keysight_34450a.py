from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from messknecht import InstrumentDataError, OverloadError

if TYPE_CHECKING:
    from messknecht import Keysight34450A


def _log(dmm: Keysight34450A) -> list[str]:
    simulation = dmm.lowlevel.simulation
    assert simulation is not None
    return simulation.log


def test_idn(sim_dmm: Keysight34450A) -> None:
    assert "34450A" in sim_dmm.idn


def test_configure_voltage_dc_defaults(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc()
    assert "CONFigure:VOLTage:DC" in _log(sim_dmm)
    assert sim_dmm.continuous is True
    assert not any("TRIGger:SOURce BUS" in entry for entry in _log(sim_dmm))


def test_configure_voltage_dc_with_range_and_resolution(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc(range=10, resolution=1.5e-6)
    assert "CONFigure:VOLTage:DC 10,1.5E-06" in _log(sim_dmm)


def test_configure_with_keyword_range(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc(range="AUTO")
    assert "CONFigure:VOLTage:DC AUTO" in _log(sim_dmm)


def test_resolution_without_range_raises(sim_dmm: Keysight34450A) -> None:
    with pytest.raises(ValueError, match="together with a range"):
        sim_dmm.configure.voltage_dc(resolution=1.5e-6)


def test_invalid_range_keyword_raises(sim_dmm: Keysight34450A) -> None:
    with pytest.raises(ValueError, match="Invalid keyword"):
        sim_dmm.configure.voltage_dc(range="TURBO")


def test_read_in_continuous_mode_uses_read_query(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc()
    value = sim_dmm.read()
    assert value == pytest.approx(1.0, abs=0.1)
    assert "READ?" in _log(sim_dmm)


def test_read_in_triggered_mode_uses_init_trg_fetch(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc(range=10, continuous=False)
    assert "TRIGger:SOURce BUS" in _log(sim_dmm)
    assert sim_dmm.continuous is False
    value = sim_dmm.read()
    assert value == pytest.approx(1.0, abs=0.1)
    log = _log(sim_dmm)
    assert "INITiate" in log
    assert "*TRG" in log
    assert "FETCh?" in log
    assert "READ?" not in log


def test_manual_triggered_flow(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc(continuous=False)
    sim_dmm.initiate()
    sim_dmm.trigger()
    assert isinstance(sim_dmm.fetch(), float)
    sim_dmm.abort()
    assert "ABORt" in _log(sim_dmm)


def test_other_functions_send_their_configure_command(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.resistance(range=1000)
    sim_dmm.configure.current_dc()
    sim_dmm.configure.frequency()
    sim_dmm.configure.continuity()
    log = _log(sim_dmm)
    assert "CONFigure:RESistance 1000" in log
    assert "CONFigure:CURRent:DC" in log
    assert "CONFigure:FREQuency" in log
    assert "CONFigure:CONTinuity" in log


def test_overload_raises(sim_dmm: Keysight34450A) -> None:
    simulation = sim_dmm.lowlevel.simulation
    assert simulation is not None
    original = simulation.backend.handle_query

    def overloaded(command: str) -> str | None:
        if command.strip().upper() == "READ?":
            return "+9.90000000E+37"
        return original(command)

    simulation.backend.handle_query = overloaded  # type: ignore[method-assign]
    sim_dmm.configure.voltage_dc()
    with pytest.raises(OverloadError, match="overload"):
        sim_dmm.read()


def test_invalid_trigger_source_raises(sim_dmm: Keysight34450A) -> None:
    with pytest.raises(ValueError, match="trigger source"):
        sim_dmm.lowlevel.set_trigger_source("SOMETIMES")


def test_get_configuration_queries_and_returns_the_response(sim_dmm: Keysight34450A) -> None:
    configuration = sim_dmm.lowlevel.get_configuration()
    assert "CONFigure?" in _log(sim_dmm)
    assert "VOLT" in configuration


def test_read_samples_continuous(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc()
    samples = sim_dmm.read_samples(10)
    assert samples.values.size == 10
    assert samples.mean == pytest.approx(1.0, abs=0.1)
    assert samples.std >= 0.0
    assert samples.min <= samples.mean <= samples.max
    log = _log(sim_dmm)
    assert log[-3:] == ["SAMPle:COUNt 10", "READ?", "SAMPle:COUNt 1"]


def test_read_samples_triggered(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc(continuous=False)
    samples = sim_dmm.read_samples(5)
    assert samples.values.size == 5
    log = _log(sim_dmm)
    assert log[-5:] == ["SAMPle:COUNt 5", "INITiate", "*TRG", "FETCh?", "SAMPle:COUNt 1"]


def test_read_samples_single_reading_has_nan_std(sim_dmm: Keysight34450A) -> None:
    sim_dmm.configure.voltage_dc()
    assert math.isnan(sim_dmm.read_samples(1).std)


def test_read_samples_invalid_count_raises(sim_dmm: Keysight34450A) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        sim_dmm.read_samples(0)


def test_read_samples_wrong_reading_count_raises(sim_dmm: Keysight34450A) -> None:
    simulation = sim_dmm.lowlevel.simulation
    assert simulation is not None
    simulation.backend.handle_query = lambda command: "+1.0E+00,+2.0E+00"  # type: ignore[method-assign]
    sim_dmm.configure.voltage_dc()
    with pytest.raises(InstrumentDataError, match="2 readings, expected 3"):
        sim_dmm.read_samples(3)
    assert _log(sim_dmm)[-1] == "SAMPle:COUNt 1"


def test_read_samples_overload_raises(sim_dmm: Keysight34450A) -> None:
    simulation = sim_dmm.lowlevel.simulation
    assert simulation is not None
    simulation.backend.handle_query = lambda command: "+1.0E+00,+9.9E+37"  # type: ignore[method-assign]
    sim_dmm.configure.voltage_dc()
    with pytest.raises(OverloadError):
        sim_dmm.read_samples(2)
