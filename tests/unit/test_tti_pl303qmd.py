from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from messknecht import CurrentRange

if TYPE_CHECKING:
    from messknecht import TTiPL303QMD


def _log(psu: TTiPL303QMD) -> list[str]:
    simulation = psu.lowlevel.simulation
    assert simulation is not None
    return simulation.log


def test_idn(sim_psu: TTiPL303QMD) -> None:
    assert "PL303QMD" in sim_psu.idn


def test_set_voltage_emits_command(sim_psu: TTiPL303QMD) -> None:
    sim_psu.ch1.voltage = 5.0
    assert "V1 5" in _log(sim_psu)


def test_set_current_limit_emits_command(sim_psu: TTiPL303QMD) -> None:
    sim_psu.ch2.current_limit = 0.25
    assert "I2 0.25" in _log(sim_psu)


def test_readbacks_query_and_return_floats(sim_psu: TTiPL303QMD) -> None:
    # Setpoint round-trip is not simulated; the typed helper returns a default,
    # but the read must still send the query and parse a float back.
    assert isinstance(sim_psu.ch1.voltage, float)
    assert isinstance(sim_psu.ch1.measured_voltage, float)
    assert isinstance(sim_psu.ch1.measured_current, float)
    log = _log(sim_psu)
    assert "V1?" in log
    assert "V1O?" in log
    assert "I1O?" in log


def test_output_toggle_emits_commands(sim_psu: TTiPL303QMD) -> None:
    sim_psu.ch1.output = True
    sim_psu.ch1.output = False
    log = _log(sim_psu)
    assert "OP1 1" in log
    assert "OP1 0" in log


def test_output_all_emits_command(sim_psu: TTiPL303QMD) -> None:
    sim_psu.output_all(True)
    assert "OPALL 1" in _log(sim_psu)


def test_protection_setters_emit_commands(sim_psu: TTiPL303QMD) -> None:
    sim_psu.ch1.ovp = 12.0
    sim_psu.ch1.ocp = 1.5
    log = _log(sim_psu)
    assert "OVP1 12" in log
    assert "OCP1 1.5" in log


def test_configure_emits_all_setpoints(sim_psu: TTiPL303QMD) -> None:
    sim_psu.configure(channel=2, voltage=7.5, current_limit=0.05, output=True)
    log = _log(sim_psu)
    assert "V2 7.5" in log
    assert "I2 0.05" in log
    assert "OP2 1" in log


def test_current_range_setter_emits_command(sim_psu: TTiPL303QMD) -> None:
    sim_psu.ch1.current_range = CurrentRange.LOW
    assert "IRANGE1 1" in _log(sim_psu)


def test_current_range_readback_type(sim_psu: TTiPL303QMD) -> None:
    assert isinstance(sim_psu.ch1.current_range, CurrentRange)


def test_invalid_channel_raises(sim_psu: TTiPL303QMD) -> None:
    with pytest.raises(ValueError, match="Channel must be"):
        sim_psu.channel(3)


def test_channels_tuple(sim_psu: TTiPL303QMD) -> None:
    assert len(sim_psu.channels) == 2
    assert sim_psu.channels[0].number == 1
    assert sim_psu.channel(2) is sim_psu.ch2


def test_check_errors_passes(sim_psu: TTiPL303QMD) -> None:
    sim_psu.check_errors()


def test_trip_reset_and_local_emit_commands(sim_psu: TTiPL303QMD) -> None:
    sim_psu.trip_reset()
    sim_psu.local()
    log = _log(sim_psu)
    assert "TRIPRST" in log
    assert "LOCAL" in log
