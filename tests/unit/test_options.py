from __future__ import annotations

import pytest

from messknecht.core.exceptions import OptionStringError
from messknecht.core.options import option_as_bool, option_as_float, parse_option_string


def test_empty_string_gives_empty_dict() -> None:
    assert parse_option_string("") == {}
    assert parse_option_string("  ") == {}


def test_key_value_pairs_are_parsed() -> None:
    options = parse_option_string("simulate=true, timeout=5000")
    assert options == {"simulate": "true", "timeout": "5000"}


def test_semicolons_and_case_and_whitespace() -> None:
    options = parse_option_string(" SIMULATE = True ;timeout=1e3 ")
    assert options == {"simulate": "True", "timeout": "1e3"}


def test_pair_without_equals_raises() -> None:
    with pytest.raises(OptionStringError, match="key=value"):
        parse_option_string("simulate")


def test_pair_without_key_raises() -> None:
    with pytest.raises(OptionStringError, match="key=value"):
        parse_option_string("=true")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("ON", True), ("false", False), ("0", False), ("off", False)],
)
def test_option_as_bool_values(raw: str, expected: bool) -> None:
    assert option_as_bool({"simulate": raw}, "simulate", default=not expected) is expected


def test_option_as_bool_default_and_invalid() -> None:
    assert option_as_bool({}, "simulate", default=True) is True
    with pytest.raises(OptionStringError, match="boolean"):
        option_as_bool({"simulate": "maybe"}, "simulate", default=False)


def test_option_as_float_default_and_invalid() -> None:
    assert option_as_float({"timeout": "2500"}, "timeout", default=1.0) == 2500.0
    assert option_as_float({}, "timeout", default=1.0) == 1.0
    with pytest.raises(OptionStringError, match="number"):
        option_as_float({"timeout": "soon"}, "timeout", default=1.0)
