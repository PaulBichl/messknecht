"""Small helpers for building and parsing SCPI messages."""

from __future__ import annotations

import re

from messknecht.core.exceptions import InstrumentDataError

_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?")


def scpi_number(value: float) -> str:
    """Format a number for use in a SCPI command (no locale surprises)."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return f"{value:.12G}"


def scpi_bool(value: bool) -> str:
    """Format a boolean as SCPI ``1``/``0``."""
    return "1" if value else "0"


def scpi_value(value: float | str, keywords: tuple[str, ...]) -> str:
    """Format a numeric-or-keyword parameter (e.g. range: ``10`` or ``"AUTO"``).

    Args:
        value: A number, or one of the allowed SCPI keywords (case insensitive).
        keywords: Allowed keywords, upper case (e.g. ``("AUTO", "MIN", "MAX", "DEF")``).

    Raises:
        ValueError: If a string value is not one of the allowed keywords.
    """
    if isinstance(value, str):
        keyword = value.strip().upper()
        if keyword not in keywords:
            msg = f"Invalid keyword {value!r}; allowed: {', '.join(keywords)} or a number"
            raise ValueError(msg)
        return keyword
    return scpi_number(value)


def parse_last_float(response: str) -> float:
    """Extract the last floating point number from an instrument response.

    Useful for responses that echo the command or append a unit, e.g. the TTi
    PL303QMD answers ``V1?`` with ``"V1 5.000"`` and ``V1O?`` with ``"5.001V"``.
    """
    matches = _FLOAT_RE.findall(response)
    if not matches:
        msg = f"Could not parse a number from instrument response {response!r}"
        raise InstrumentDataError(msg)
    return float(matches[-1])


def parse_scpi_bool(response: str) -> bool:
    """Parse a SCPI boolean response (``0``/``1``/``ON``/``OFF``)."""
    value = response.strip().upper()
    if value in {"1", "ON"}:
        return True
    if value in {"0", "OFF"}:
        return False
    msg = f"Could not parse boolean from instrument response {response!r}"
    raise InstrumentDataError(msg)


def parse_leading_error_code(response: str) -> int:
    """Parse the numeric error code at the start of a ``SYSTem:ERRor?`` response."""
    match = re.match(r"\s*([-+]?\d+)", response)
    if match is None:
        msg = f"Could not parse error code from instrument response {response!r}"
        raise InstrumentDataError(msg)
    return int(match.group(1))
