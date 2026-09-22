"""Lab integration test for the Keysight DSO-X 3014T oscilloscope.

Feed any signal (e.g. the probe compensation output) into channel 1, then::

    hatch run test tests/integration/test_scope_lab.py --scope "USB0::...::INSTR" -s

The screenshot/CSV paths are printed so you can inspect the files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from messknecht import KeysightDSOX3000T
from tests.conftest import integration_resource

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.integration


@pytest.fixture
def scope(request: pytest.FixtureRequest) -> Iterator[KeysightDSOX3000T]:
    instrument = KeysightDSOX3000T()
    # No reset: keep the setup the user prepared at the instrument.
    instrument.initialize(integration_resource(request, "--scope"), False)
    yield instrument
    instrument.run()  # leave the scope running for the user
    instrument.close()


def test_identification(scope: KeysightDSOX3000T) -> None:
    idn = scope.idn
    print(f"\nScope *IDN? -> {idn}")
    assert "3014T" in idn or "DSO-X" in idn


def test_screenshot(scope: KeysightDSOX3000T, tmp_path: Path) -> None:
    target = scope.screenshot(tmp_path / "scope_screen.png")
    size = target.stat().st_size
    print(f"\nScreenshot saved to {target} ({size} bytes) - please open and confirm")
    assert target.read_bytes().startswith(b"\x89PNG")
    assert size > 10_000  # a real screen dump is tens of kilobytes


def test_waveform_to_csv(scope: KeysightDSOX3000T, tmp_path: Path) -> None:
    target = scope.save_waveform_csv(tmp_path / "scope_waveform.csv", channels=[1], points=1000)
    lines = target.read_text().splitlines()
    print(f"\nWaveform CSV saved to {target} ({len(lines) - 1} samples)")
    print(f"  header: {lines[0]}")
    print(f"  first : {lines[1]}")
    assert lines[0].startswith("time_s,")
    # :WAVeform:POINts is a request - the scope may return fewer points.
    assert 100 <= len(lines) - 1 <= 1000


def test_waveform_measurement(scope: KeysightDSOX3000T) -> None:
    vpp = scope.measure_vpp(1)
    frequency = scope.measure_frequency(1)
    print(f"\nCH1 measurements: Vpp={vpp:.4g} V, f={frequency:.6g} Hz (please sanity check)")
    assert vpp > 0.0  # a flat line means nothing is connected to CH1


def test_no_pending_instrument_errors(scope: KeysightDSOX3000T) -> None:
    scope.check_errors()
