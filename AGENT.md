# Agent Instructions

Guide for Claude, Copilot, and other AI assistants on code style and project patterns.

## What this project is

**messknecht** is an instrument driver library (lab automation) on top of pyvisa.
Read `docs/developer-guide.md` before touching driver code — it explains the
architecture and the design decisions. Instrument programming manuals are in
`manuals/`; the SCPI command in a low level method's docstring must match the manual.

## Project Setup

- **Language**: Python 3.12+
- **Package Manager**: Hatch with uv
- **Code Quality**: Ruff (lint/format) + Mypy (type checking) + Pre-commit
- **Testing**: Pytest
- **Runtime deps**: pyvisa, numpy

## Project Structure

```
src/messknecht/
├── core/                     # instrument-independent building blocks
│   ├── instrument.py         # VisaInstrument (low level base) + InstrumentApplication
│   ├── simulation.py         # simulation backend/session
│   ├── options.py            # option string parsing
│   ├── scpi.py               # SCPI format/parse helpers
│   └── exceptions.py         # MessknechtError hierarchy
├── instruments/              # ONE module per instrument containing, in order:
│   │                         #   _XxxSimulation, XxxLowLevel, Xxx (application layer)
│   ├── tti_pl303qmd.py
│   ├── keysight_dsox3000t.py
│   ├── keysight_33500b.py
│   └── keysight_34450a.py
└── main.py                   # python -m messknecht → list VISA resources

tests/
├── conftest.py               # sim fixtures + integration CLI options (--psu, --scope, ...)
├── unit/                     # fast, run against simulation
└── integration/              # short lab scripts, skip without a --<instrument> resource

examples/                     # short user-facing scripts (edit the VISA address, then run)
docs/                         # user-guide.md, developer-guide.md
```

## Driver rules (important)

- Low level drivers subclass `VisaInstrument`; **one method ≈ one SCPI command**,
  docstring names the exact command. All I/O through the typed helpers
  (`write`, `query`, `query_float`, `query_bool`, `query_binary_block`) —
  never touch the pyvisa resource directly.
- Application classes subclass `InstrumentApplication[TheLowLevel]` and own
  `self._lowlevel`; they compose low level calls and call `check_errors()`
  once at the end of configure-style methods.
- Errors: raise exceptions from `core/exceptions.py`; **no logging**.
  API misuse (bad channel/keyword) raises plain `ValueError`.
- Give each driver a `SimulationBackend` in the same module — normally just an
  `IDN` override. Unhandled simulated queries fall back to typed defaults, or
  raise `SimulationError` for plain string/binary reads. Do **not** build
  stateful per-command simulators to make round-trip assertions pass; assert on
  `simulation.log` instead. (The scope is the one exception: it returns
  synthetic binary data, which has no numeric default to fall back to.)
- Export new classes in `instruments/__init__.py` **and** `messknecht/__init__.py`
  (`__all__` stays sorted — ruff enforces it).
- New driver? Follow the checklist in `docs/developer-guide.md`.

## Code Patterns

### Imports

Every file starts with `from __future__ import annotations`. Typing-only
imports go into an `if TYPE_CHECKING:` block (ruff TC rules). Absolute
imports only.

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from messknecht.core.instrument import VisaInstrument

if TYPE_CHECKING:
    from collections.abc import Sequence
```

### Type Hints

Always use type hints (`X | None`, not `Optional[X]`):

```python
def set_voltage(self, channel: int, volts: float) -> None:
    """``V<n> <nrf>`` - set the output voltage."""
    self.write(f"V{channel} {scpi_number(volts)}")
```

### Raising errors

Ruff's EM rules: assign the message to a variable first, never a (f-)string
literal inside `raise`:

```python
if not 1 <= channel <= self.CHANNEL_COUNT:
    msg = f"Channel must be 1..{self.CHANNEL_COUNT}, got {channel}"
    raise ValueError(msg)
```

### Docstrings

Brief docstrings; Args/Returns/Raises sections for non-trivial public
functions (see `Keysight33500B.load_arbitrary` for the expected style).

## Testing

- Unit tests run against the simulation fixtures from `tests/conftest.py`
  (`sim_psu`, `sim_scope`, `sim_wfg`, `sim_dmm`) and assert on the SCPI
  traffic via `instrument.lowlevel.simulation.log` — verify the *commands
  emitted*, not simulated readback values (which are defaults).
- Integration tests are short printing lab scripts that answer "does this
  work at the bench?"; fixture pattern: `integration_resource(request,
  "--dmm")`, safe teardown (outputs off). They always talk to real
  instruments and skip without a resource - never add simulation branches
  to them; anything checkable without hardware belongs in a unit test.
- Run everything without hardware: `hatch run test` (the lab tests skip).

## Commands

| Command | Purpose |
|---------|---------|
| `hatch run type` | Type checking (mypy on `src`, `tests`, `examples`) |
| `hatch run style` | Lint check (ruff) |
| `hatch run fix` | Auto-fix style & run pre-commit |
| `hatch run test` | Run tests (pytest) |
| `hatch run test --cov=src` | Run with coverage |

Always run `hatch run style`, `hatch run type` and `hatch run test` before
declaring work done.

## Naming Conventions

- **Modules**: `snake_case`, drivers as `<vendor>_<model>.py`
- **Classes**: `PascalCase`; drivers `<Vendor><Model>` + `<Vendor><Model>LowLevel`
- **Functions/Methods**: `snake_case` (ruff N802 is enforced)
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: prefix with `_`

## Do's and Don'ts

### ✅ Do

- Verify SCPI syntax against the manual in `manuals/` before adding a command
- Keep the application layer small; expose the rest via `instrument.lowlevel`
- Add unit tests (simulation) for every new driver method
- Use the typed query helpers so simulation keeps working

### ❌ Don't

- Log or print from library code (raise exceptions instead)
- Talk to `self._resource` directly in drivers
- Grow the scope driver into a full instrument UI (see instruction.md)
- Leave `__all__` unsorted or skip `from __future__ import annotations`
