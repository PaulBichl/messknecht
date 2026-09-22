from __future__ import annotations

import csv
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from messknecht import KeysightDSOX3000T


def _log(scope: KeysightDSOX3000T) -> list[str]:
    simulation = scope.lowlevel.simulation
    assert simulation is not None
    return simulation.log


def test_idn(sim_scope: KeysightDSOX3000T) -> None:
    assert "DSO-X 3014T" in sim_scope.idn


def test_get_waveform_shape_and_scaling(sim_scope: KeysightDSOX3000T) -> None:
    waveform = sim_scope.get_waveform(channel=1, points=500)
    assert waveform.source == "CHANnel1"
    assert waveform.voltage.size == 500
    assert waveform.time.size == 500
    # Simulation: fixed +/-3 V sine (see _KeysightDSOX3000TSimulation).
    assert waveform.voltage.max() == pytest.approx(3.0, rel=0.05)
    assert waveform.voltage.min() == pytest.approx(-3.0, rel=0.05)
    # Simulation: 100 us/div -> 1 ms across the 10 division screen.
    span = waveform.time[-1] - waveform.time[0]
    assert span == pytest.approx(1e-3, rel=0.05)
    assert waveform.preamble.points == 500


def test_get_waveform_uses_word_format(sim_scope: KeysightDSOX3000T) -> None:
    sim_scope.get_waveform(channel=2)
    log = _log(sim_scope)
    assert ":WAVeform:SOURce CHANnel2" in log
    assert ":WAVeform:FORMat WORD" in log
    assert ":WAVeform:UNSigned 1" in log
    assert ":WAVeform:BYTeorder LSBFirst" in log
    assert ":WAVeform:DATA?" in log


def test_save_waveform_csv(sim_scope: KeysightDSOX3000T, tmp_path: Path) -> None:
    target = tmp_path / "waveform.csv"
    written = sim_scope.save_waveform_csv(target, channels=[1, 2], points=250)
    assert written == target
    assert ":DIGitize CHANnel1,CHANnel2" in _log(sim_scope)
    with target.open() as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["time_s", "channel1_V", "channel2_V"]
    assert len(rows) == 1 + 250
    values = [float(cell) for cell in rows[1]]
    assert len(values) == 3


def test_save_waveform_csv_single_channel_without_acquire(sim_scope: KeysightDSOX3000T, tmp_path: Path) -> None:
    target = tmp_path / "single.csv"
    sim_scope.save_waveform_csv(target, channels=1, acquire=False)
    assert not any(entry.startswith(":DIGitize") for entry in _log(sim_scope))
    assert target.exists()


def test_screenshot_png(sim_scope: KeysightDSOX3000T, tmp_path: Path) -> None:
    target = sim_scope.screenshot(tmp_path / "screen.png")
    data = target.read_bytes()
    assert data.startswith(b"\x89PNG")
    assert ":HARDcopy:INKSaver 0" in _log(sim_scope)


def test_screenshot_bmp_grayscale(sim_scope: KeysightDSOX3000T, tmp_path: Path) -> None:
    target = sim_scope.screenshot(tmp_path / "screen.bmp", palette="grayscale")
    assert target.read_bytes().startswith(b"BM")
    assert any("GRAYscale" in entry for entry in _log(sim_scope))


def test_screenshot_invalid_suffix_and_palette(sim_scope: KeysightDSOX3000T, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported screenshot format"):
        sim_scope.screenshot(tmp_path / "screen.jpg")
    with pytest.raises(ValueError, match="Invalid palette"):
        sim_scope.screenshot(tmp_path / "screen.png", palette="sepia")


def test_setup_channel_and_timebase(sim_scope: KeysightDSOX3000T) -> None:
    sim_scope.setup_channel(1, scale=0.5, offset=0.25, coupling="dc", probe_attenuation=10, display=True)
    sim_scope.setup_timebase(scale=1e-3, position=0.0)
    log = _log(sim_scope)
    assert ":CHANnel1:SCALe 0.5" in log
    assert ":CHANnel1:OFFSet 0.25" in log
    assert ":CHANnel1:COUPling DC" in log
    assert ":CHANnel1:PROBe 10" in log
    assert ":TIMebase:SCALe 0.001" in log


def test_setup_edge_trigger(sim_scope: KeysightDSOX3000T) -> None:
    sim_scope.setup_edge_trigger(source=2, level=1.2, slope="negative")
    log = _log(sim_scope)
    assert ":TRIGger:MODE EDGE" in log
    assert ":TRIGger:EDGE:SOURce CHANnel2" in log
    assert ":TRIGger:EDGE:LEVel 1.2" in log
    assert ":TRIGger:EDGE:SLOPe NEGative" in log


def test_invalid_arguments(sim_scope: KeysightDSOX3000T) -> None:
    with pytest.raises(ValueError, match="Channel must be"):
        sim_scope.get_waveform(channel=5)
    with pytest.raises(ValueError, match="points_mode"):
        sim_scope.get_waveform(channel=1, points_mode="turbo")
    with pytest.raises(ValueError, match="Invalid slope"):
        sim_scope.setup_edge_trigger(slope="up")
    with pytest.raises(ValueError, match="Coupling"):
        sim_scope.setup_channel(1, coupling="XY")


def test_acquisition_control_commands(sim_scope: KeysightDSOX3000T) -> None:
    sim_scope.run()
    sim_scope.stop()
    sim_scope.single()
    sim_scope.digitize(1)
    sim_scope.autoscale()
    log = _log(sim_scope)
    for command in (":RUN", ":STOP", ":SINGle", ":DIGitize CHANnel1", ":AUToscale"):
        assert command in log


def test_measurements_return_floats(sim_scope: KeysightDSOX3000T) -> None:
    assert isinstance(sim_scope.measure_vpp(1), float)
    assert sim_scope.measure_frequency(1) == pytest.approx(1000.0, abs=1.0)
    assert isinstance(sim_scope.measure_vaverage(1), float)


def test_waveform_time_axis_is_monotonic(sim_scope: KeysightDSOX3000T) -> None:
    waveform = sim_scope.get_waveform(1, points=100)
    assert np.all(np.diff(waveform.time) > 0)
