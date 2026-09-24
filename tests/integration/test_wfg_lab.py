"""Lab integration test for the Keysight 33500B waveform generator.

Connect channel 1 to a scope to confirm the waveforms, then::

    hatch run test tests/integration/test_wfg_lab.py --wfg "TCPIP0::...::INSTR" -s
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from messknecht import Keysight33500B
from tests.conftest import integration_resource

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration


@pytest.fixture
def wfg(request: pytest.FixtureRequest) -> Iterator[Keysight33500B]:
    instrument = Keysight33500B()
    instrument.initialize(integration_resource(request, "--wfg"), True)
    yield instrument
    instrument.output(False, channel=1)
    instrument.close()


def test_identification(wfg: Keysight33500B) -> None:
    idn = wfg.idn
    print(f"\nWFG *IDN? -> {idn}")
    assert "335" in idn


def test_sine_output(wfg: Keysight33500B) -> None:
    wfg.configure_sine(frequency=1e3, amplitude=1.0, offset=0.0)
    wfg.output(True)
    frequency = wfg.lowlevel.get_frequency(1)
    print(f"\n1 kHz / 1 Vpp sine on CH1 (frequency readback {frequency:.6g} Hz) - confirm on the scope")
    assert frequency == pytest.approx(1e3, rel=1e-6)
    assert wfg.lowlevel.get_output(1) is True


def test_square_with_duty_cycle(wfg: Keysight33500B) -> None:
    wfg.configure_square(frequency=2e3, amplitude=2.0, duty_cycle=25.0)
    wfg.output(True)
    print("\n2 kHz / 2 Vpp square with 25 % duty cycle on CH1 - confirm on the scope")
    wfg.check_errors()


def test_arbitrary_waveform(wfg: Keysight33500B) -> None:
    """A 100-point 'sine + 3rd harmonic' arb played at 100 kSa/s (1 kHz repetition)."""
    values = [math.sin(2.0 * math.pi * i / 100.0) + 0.3 * math.sin(6.0 * math.pi * i / 100.0) for i in range(100)]
    wfg.load_arbitrary(values, name="MESSTEST", sample_rate=100e3, amplitude=1.0, offset=0.0)
    wfg.output(True)
    print("\nArb 'MESSTEST' active on CH1 (distorted 1 kHz sine) - confirm on the scope")
    assert wfg.lowlevel.get_function(1).upper().startswith("ARB")


def test_output_load(wfg: Keysight33500B) -> None:
    wfg.set_output_load("highz")
    assert wfg.get_output_load() == math.inf
    wfg.set_output_load(50)
    assert wfg.get_output_load() == pytest.approx(50.0)


def test_no_pending_instrument_errors(wfg: Keysight33500B) -> None:
    wfg.check_errors()
