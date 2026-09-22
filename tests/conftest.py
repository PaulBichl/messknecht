"""Shared pytest fixtures and integration test command line options.

Integration tests need a VISA resource string per instrument, e.g.::

    hatch run test tests/integration --psu "USB0::0x103E::0x0402::123456::INSTR"

Without the matching option an integration test is skipped. Integration
tests always talk to real instruments - anything checkable without hardware
belongs in a unit test (those use the simulation fixtures below).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from messknecht import Keysight33500B, Keysight34450A, KeysightDSOX3000T, TTiPL303QMD

if TYPE_CHECKING:
    from collections.abc import Iterator


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("messknecht", "messknecht integration instruments")
    group.addoption("--psu", default=None, help="VISA resource of the TTi PL303QMD power supply")
    group.addoption("--scope", default=None, help="VISA resource of the Keysight DSO-X 3014T oscilloscope")
    group.addoption("--wfg", default=None, help="VISA resource of the Keysight 33500B waveform generator")
    group.addoption("--dmm", default=None, help="VISA resource of the Keysight 34450A multimeter")


def integration_resource(request: pytest.FixtureRequest, option: str) -> str:
    """Return the VISA resource for an integration fixture, or skip the test."""
    resource = request.config.getoption(option)
    if not resource:
        pytest.skip(f"pass {option} <visa-resource> to run this test")
    return str(resource)


# ---------------------------------------------------------------------------
# Simulation fixtures (used by the unit tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def sim_psu() -> Iterator[TTiPL303QMD]:
    psu = TTiPL303QMD()
    psu.initialize("SIM::psu", True, "simulate=true")
    yield psu
    psu.close()


@pytest.fixture
def sim_scope() -> Iterator[KeysightDSOX3000T]:
    scope = KeysightDSOX3000T()
    scope.initialize("SIM::scope", True, "simulate=true")
    yield scope
    scope.close()


@pytest.fixture
def sim_wfg() -> Iterator[Keysight33500B]:
    wfg = Keysight33500B()
    wfg.initialize("SIM::wfg", True, "simulate=true")
    yield wfg
    wfg.close()


@pytest.fixture
def sim_dmm() -> Iterator[Keysight34450A]:
    dmm = Keysight34450A()
    dmm.initialize("SIM::dmm", True, "simulate=true")
    yield dmm
    dmm.close()
