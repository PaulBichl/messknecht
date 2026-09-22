from __future__ import annotations

from typing import TYPE_CHECKING

import pyvisa

from messknecht.main import main

if TYPE_CHECKING:
    import pytest


class _FakeResourceManager:
    """Stands in for ``pyvisa.ResourceManager`` so the test needs no VISA backend."""

    resources: tuple[str, ...] = ()

    def list_resources(self) -> tuple[str, ...]:
        return self.resources


def _patch_resource_manager(monkeypatch: pytest.MonkeyPatch, manager: object) -> None:
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda *args, **kwargs: manager)


def test_main_lists_the_visa_resources(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    manager = _FakeResourceManager()
    manager.resources = ("USB0::0x2A8D::0x1601::MY12345678::INSTR", "ASRL/dev/ttyACM0::INSTR")
    _patch_resource_manager(monkeypatch, manager)

    exit_code = main()

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "messknecht" in captured
    for resource in manager.resources:
        assert resource in captured


def test_main_reports_an_empty_resource_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_resource_manager(monkeypatch, _FakeResourceManager())

    exit_code = main()

    assert exit_code == 0
    assert "No VISA resources found." in capsys.readouterr().out


def test_main_explains_a_missing_visa_backend(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _no_backend(*args: object, **kwargs: object) -> _FakeResourceManager:
        msg = "no backend available"
        raise ValueError(msg)

    monkeypatch.setattr(pyvisa, "ResourceManager", _no_backend)

    exit_code = main()

    captured = capsys.readouterr().out
    assert exit_code == 1
    assert "Could not query VISA resources" in captured
    assert "pyvisa-py" in captured
