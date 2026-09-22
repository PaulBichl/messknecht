from __future__ import annotations

import pytest

from messknecht.core.exceptions import InstrumentDataError
from messknecht.core.scpi import (
    parse_last_float,
    parse_leading_error_code,
    parse_scpi_bool,
    scpi_number,
    scpi_value,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(5, "5"), (5.0, "5"), (1.5e-6, "1.5E-06"), (0.5, "0.5"), (True, "1"), (False, "0")],
)
def test_scpi_number(value: float, expected: str) -> None:
    assert scpi_number(value) == expected


def test_scpi_value_accepts_keywords_and_numbers() -> None:
    assert scpi_value("auto", ("AUTO", "MIN")) == "AUTO"
    assert scpi_value(10, ("AUTO",)) == "10"


def test_scpi_value_rejects_unknown_keyword() -> None:
    with pytest.raises(ValueError, match="Invalid keyword"):
        scpi_value("banana", ("AUTO", "MIN"))


@pytest.mark.parametrize(
    ("response", "expected"),
    [("V1 5.000", 5.0), ("VP2 30.00", 30.0), ("0.5001A", 0.5001), ("-1.5e-3", -0.0015), ("1", 1.0)],
)
def test_parse_last_float(response: str, expected: float) -> None:
    assert parse_last_float(response) == pytest.approx(expected)


def test_parse_last_float_without_number_raises() -> None:
    with pytest.raises(InstrumentDataError, match="parse"):
        parse_last_float("NO NUMBERS HERE")


def test_parse_scpi_bool() -> None:
    assert parse_scpi_bool("1") is True
    assert parse_scpi_bool(" OFF ") is False
    with pytest.raises(InstrumentDataError, match="boolean"):
        parse_scpi_bool("2")


def test_parse_leading_error_code() -> None:
    assert parse_leading_error_code('+0,"No error"') == 0
    assert parse_leading_error_code('-113,"Undefined header"') == -113
    with pytest.raises(InstrumentDataError, match="error code"):
        parse_leading_error_code("garbage")
