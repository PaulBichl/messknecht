"""Lab integration test for the TTi PL303QMD power supply.

Run with real hardware (nothing should be connected to the outputs)::

    hatch run test tests/integration/test_psu_lab.py --psu "ASRL/dev/ttyACM0::INSTR" -s
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from messknecht import TTiPL303QMD
from tests.conftest import integration_resource

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

#: Let the output settle before measuring it back.
SETTLE_S = 0.5


@pytest.fixture
def psu(request: pytest.FixtureRequest) -> Iterator[TTiPL303QMD]:
    instrument = TTiPL303QMD()
    instrument.initialize(integration_resource(request, "--psu"), True)
    yield instrument
    instrument.output_all(False)
    instrument.local()
    instrument.close()


def test_identification(psu: TTiPL303QMD) -> None:
    idn = psu.idn
    print(f"\nPSU *IDN? -> {idn}")
    assert "PL303" in idn.upper()


def test_voltage_setpoint_roundtrip(psu: TTiPL303QMD) -> None:
    psu.ch1.configure(voltage=1.5, current_limit=0.1)
    readback = psu.ch1.voltage
    print(f"\nCH1 setpoint 1.500 V -> readback {readback:.3f} V")
    assert readback == pytest.approx(1.5, abs=0.01)


def test_output_voltage_readback(psu: TTiPL303QMD) -> None:
    """Set 5 V on channel 1, enable the output and measure it (open circuit)."""
    psu.ch1.configure(voltage=5.0, current_limit=0.05)
    psu.ch1.output = True
    time.sleep(SETTLE_S)

    measured = psu.ch1.measured_voltage
    current = psu.ch1.measured_current
    print(f"\nCH1 output on: measured {measured:.3f} V / {current:.4f} A (please confirm on the display)")
    assert measured == pytest.approx(5.0, rel=0.05)

    psu.ch1.output = False
    time.sleep(SETTLE_S)
    assert psu.ch1.output is False


def test_second_channel(psu: TTiPL303QMD) -> None:
    psu.ch2.configure(voltage=2.5, current_limit=0.05)
    print(f"\nCH2 setpoint -> {psu.ch2.voltage:.3f} V, limit {psu.ch2.current_limit:.3f} A")
    assert psu.ch2.voltage == pytest.approx(2.5, abs=0.01)
    assert psu.ch2.current_limit == pytest.approx(0.05, abs=0.001)


def test_no_pending_instrument_errors(psu: TTiPL303QMD) -> None:
    psu.check_errors()
