from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from messknecht import Keysight33500B


def _log(wfg: Keysight33500B) -> list[str]:
    simulation = wfg.lowlevel.simulation
    assert simulation is not None
    return simulation.log


def test_idn(sim_wfg: Keysight33500B) -> None:
    assert "335" in sim_wfg.idn


def test_configure_sine(sim_wfg: Keysight33500B) -> None:
    sim_wfg.configure_sine(frequency=1000.0, amplitude=2.0, offset=0.5)
    log = _log(sim_wfg)
    assert any(entry.startswith("SOURce1:FUNCtion SIN") for entry in log)
    assert "SOURce1:FREQuency 1000" in log
    assert "SOURce1:VOLTage 2" in log
    assert "SOURce1:VOLTage:OFFSet 0.5" in log


def test_configure_square_with_duty_cycle(sim_wfg: Keysight33500B) -> None:
    sim_wfg.configure_square(frequency=500.0, amplitude=1.0, duty_cycle=25.0, channel=2)
    log = _log(sim_wfg)
    assert any(entry.startswith("SOURce2:FUNCtion SQU") for entry in log)
    assert "SOURce2:FUNCtion:SQUare:DCYCle 25" in log


def test_configure_ramp_and_dc_and_noise(sim_wfg: Keysight33500B) -> None:
    sim_wfg.configure_ramp(frequency=10.0, amplitude=1.0, symmetry=50.0)
    sim_wfg.configure_noise(amplitude=0.5)
    sim_wfg.configure_dc(offset=1.25)
    log = _log(sim_wfg)
    assert "SOURce1:FUNCtion:RAMP:SYMMetry 50" in log
    assert "SOURce1:VOLTage:OFFSet 1.25" in log


def test_configure_pulse_width_and_duty_cycle_conflict(sim_wfg: Keysight33500B) -> None:
    with pytest.raises(ValueError, match="not both"):
        sim_wfg.configure_pulse(frequency=1e3, width=1e-4, duty_cycle=10.0)


def test_invalid_function_raises(sim_wfg: Keysight33500B) -> None:
    with pytest.raises(ValueError, match="Invalid function"):
        sim_wfg.lowlevel.set_function(1, "TRIANGLE")


def test_invalid_channel_raises(sim_wfg: Keysight33500B) -> None:
    with pytest.raises(ValueError, match="Channel must be"):
        sim_wfg.configure_sine(frequency=1.0, channel=3)


def test_output_toggle_emits_commands(sim_wfg: Keysight33500B) -> None:
    sim_wfg.output(True)
    sim_wfg.output(False)
    log = _log(sim_wfg)
    assert "OUTPut1 1" in log
    assert "OUTPut1 0" in log


def test_numeric_readback_returns_float_in_simulation(sim_wfg: Keysight33500B) -> None:
    # Round-trip is not simulated; the typed helper returns a default.
    assert isinstance(sim_wfg.lowlevel.get_frequency(1), float)
    assert "SOURce1:FREQuency?" in _log(sim_wfg)


def test_load_arbitrary_downloads_and_activates(sim_wfg: Keysight33500B) -> None:
    values = [math.sin(2.0 * math.pi * i / 100.0) for i in range(100)]
    sim_wfg.load_arbitrary(values, name="TESTARB", sample_rate=10000.0, amplitude=2.0, offset=0.0)
    log = _log(sim_wfg)
    assert "SOURce1:DATA:VOLatile:CLEar" in log
    assert any(entry.startswith("SOURce1:DATA:ARBitrary TESTARB,") for entry in log)
    assert "SOURce1:FUNCtion:ARBitrary TESTARB" in log
    assert "SOURce1:FUNCtion:ARBitrary:SRATe 10000" in log
    assert any(entry.startswith("SOURce1:FUNCtion ARB") for entry in log)


def test_load_arbitrary_normalizes(sim_wfg: Keysight33500B) -> None:
    sim_wfg.load_arbitrary([0.0, 5.0, -10.0, 5.0, 0.0, 5.0, -5.0, 2.5], name="NORM")
    download = next(entry for entry in _log(sim_wfg) if entry.startswith("SOURce1:DATA:ARBitrary NORM,"))
    payload = download.split(",", 1)[1].split(",")
    numbers = [float(token) for token in payload]
    assert max(abs(number) for number in numbers) == pytest.approx(1.0)


def test_load_arbitrary_validation(sim_wfg: Keysight33500B) -> None:
    with pytest.raises(ValueError, match="Arb length"):
        sim_wfg.load_arbitrary([0.0, 1.0])
    with pytest.raises(ValueError, match="Invalid arb name"):
        sim_wfg.load_arbitrary([0.0, 1.0] * 8, name="1BADNAME")
    with pytest.raises(ValueError, match="all-zero"):
        sim_wfg.load_arbitrary([0.0] * 16)
    with pytest.raises(ValueError, match=r"within -1\.0"):
        sim_wfg.load_arbitrary([0.0, 2.0] * 8, normalize=False)


def test_load_arbitrary_csv(sim_wfg: Keysight33500B, tmp_path: Path) -> None:
    csv_file = tmp_path / "my wave-form.csv"
    lines = ["value", "# a comment", *(f"{math.sin(2.0 * math.pi * i / 64.0):.5f}" for i in range(64))]
    csv_file.write_text("\n".join(lines))
    sim_wfg.load_arbitrary_csv(csv_file, sample_rate=6400.0)
    download = next(entry for entry in _log(sim_wfg) if ":DATA:ARBitrary" in entry)
    name = download.split(" ", 1)[1].split(",", 1)[0]
    assert name == "my_wave_form"
    payload = download.split(",", 1)[1].split(",")
    assert len(payload) == 64


def test_load_arbitrary_csv_comma_separated(sim_wfg: Keysight33500B, tmp_path: Path) -> None:
    csv_file = tmp_path / "ramp.csv"
    csv_file.write_text(",".join(str(i / 10.0) for i in range(10)))
    sim_wfg.load_arbitrary_csv(csv_file, name="RAMP10")
    download = next(entry for entry in _log(sim_wfg) if ":DATA:ARBitrary" in entry)
    assert len(download.split(",")) == 1 + 10


def test_load_arbitrary_csv_missing_file(sim_wfg: Keysight33500B, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        sim_wfg.load_arbitrary_csv(tmp_path / "missing.csv")


def test_set_output_load(sim_wfg: Keysight33500B) -> None:
    sim_wfg.set_output_load(50)
    sim_wfg.set_output_load("INFinity")
    log = _log(sim_wfg)
    assert "OUTPut1:LOAD 50" in log
    assert "OUTPut1:LOAD INFINITY" in log
    with pytest.raises(ValueError, match="Invalid load"):
        sim_wfg.set_output_load("HEAVY")
