"""Lab integration test for the Keysight 34450A multimeter.

Works with open inputs (reads ~0 V); connect a known voltage for a better check::

    hatch run test tests/integration/test_dmm_lab.py --dmm "USB0::...::INSTR" -s
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from messknecht import Keysight34450A
from tests.conftest import integration_resource

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration


@pytest.fixture
def dmm(request: pytest.FixtureRequest) -> Iterator[Keysight34450A]:
    instrument = Keysight34450A()
    instrument.initialize(integration_resource(request, "--dmm"), True)
    yield instrument
    instrument.close()


def test_identification(dmm: Keysight34450A) -> None:
    idn = dmm.idn
    print(f"\nDMM *IDN? -> {idn}")
    assert "34450A" in idn


def test_voltage_dc_continuous(dmm: Keysight34450A) -> None:
    dmm.configure.voltage_dc()
    readings = [dmm.read() for _ in range(3)]
    print(f"\nDC voltage (auto range, continuous): {[f'{value:.6g} V' for value in readings]}")
    assert len(readings) == 3


def test_voltage_dc_fixed_range(dmm: Keysight34450A) -> None:
    dmm.configure.voltage_dc(range=10, resolution=3.0e-5)
    value = dmm.read()
    print(f"\nDC voltage (10 V range): {value:.6g} V")
    assert -10.5 <= value <= 10.5


def test_voltage_dc_triggered_mode(dmm: Keysight34450A) -> None:
    dmm.configure.voltage_dc(range=10, continuous=False)
    value = dmm.read()  # INITiate + *TRG + FETCh?
    print(f"\nDC voltage (triggered/BUS mode): {value:.6g} V")
    assert -10.5 <= value <= 10.5

    dmm.initiate()
    dmm.trigger()
    fetched = dmm.fetch()
    print(f"Explicit INIT/*TRG/FETCh? -> {fetched:.6g} V")
    assert -10.5 <= fetched <= 10.5


def test_configuration_query(dmm: Keysight34450A) -> None:
    dmm.configure.voltage_dc(range=10)
    configuration = dmm.lowlevel.get_configuration()
    print(f"\nCONF? -> {configuration}")
    assert "VOLT" in configuration.upper()


def test_no_pending_instrument_errors(dmm: Keysight34450A) -> None:
    dmm.check_errors()
