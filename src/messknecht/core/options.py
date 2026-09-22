"""Parsing of the ``option_string`` argument of ``initialize()``.

The option string is a list of ``key=value`` pairs separated by commas or
semicolons, e.g. ``"simulate=true, timeout=10000"``. Keys are case
insensitive; surrounding whitespace is ignored. Unknown keys are kept and can
be read by drivers, so driver specific options do not require changes in the
core.

Well-known keys understood by :class:`~messknecht.core.instrument.VisaInstrument`:

========================  =====================================================
``simulate``              ``true``/``false`` - run against the simulation
                          backend instead of real hardware (default ``false``).
``timeout``               VISA I/O timeout in milliseconds.
``error_check``           ``true``/``false`` - query the instrument error queue
                          after every write and raise on errors (slow, useful
                          for debugging; default ``false``).
``visa_library``          Passed to :class:`pyvisa.ResourceManager`, e.g.
                          ``@py`` to force the pure Python pyvisa-py backend.
========================  =====================================================
"""

from __future__ import annotations

from messknecht.core.exceptions import OptionStringError

_TRUE_VALUES = {"true", "1", "on", "yes"}
_FALSE_VALUES = {"false", "0", "off", "no"}


def parse_option_string(option_string: str) -> dict[str, str]:
    """Parse an option string into a dict with lower-case keys.

    Args:
        option_string: e.g. ``"simulate=true, timeout=5000"``. Empty strings
            are allowed and yield an empty dict.

    Returns:
        Mapping of lower-case key to the raw (stripped) value string.

    Raises:
        OptionStringError: If a pair is not of the form ``key=value``.
    """
    options: dict[str, str] = {}
    for raw_pair in option_string.replace(";", ",").split(","):
        pair = raw_pair.strip()
        if not pair:
            continue
        key, separator, value = pair.partition("=")
        key = key.strip().lower()
        if not separator or not key:
            msg = f"Invalid option {pair!r}: expected 'key=value' pairs separated by ',' or ';'"
            raise OptionStringError(msg)
        options[key] = value.strip()
    return options


def option_as_bool(options: dict[str, str], key: str, default: bool) -> bool:
    """Read a boolean option (accepts true/false, 1/0, on/off, yes/no)."""
    raw = options.get(key)
    if raw is None:
        return default
    value = raw.lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    msg = f"Option {key!r} expects a boolean, got {raw!r}"
    raise OptionStringError(msg)


def option_as_float(options: dict[str, str], key: str, default: float) -> float:
    """Read a numeric option."""
    raw = options.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        msg = f"Option {key!r} expects a number, got {raw!r}"
        raise OptionStringError(msg) from exc
