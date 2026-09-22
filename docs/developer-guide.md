# Developer Guide

Architecture, design decisions and a recipe for adding new instrument drivers.

## Package layout

```
src/messknecht/
├── core/                        # instrument-independent building blocks
│   ├── instrument.py            # VisaInstrument (low level base), InstrumentApplication
│   ├── simulation.py            # SimulationBackend, SimulatedSession
│   ├── options.py               # option string parsing (simulate=true, ...)
│   ├── scpi.py                  # SCPI formatting/parsing helpers
│   └── exceptions.py            # MessknechtError hierarchy
├── instruments/                 # one module per instrument
│   ├── tti_pl303qmd.py          # TTiPL303QMDLowLevel + TTiPL303QMD (+ sim backend)
│   ├── keysight_dsox3000t.py
│   ├── keysight_33500b.py
│   └── keysight_34450a.py
└── main.py                      # python -m messknecht → list VISA resources
```

## Layering

Every instrument module contains (in this order) the **simulation backend**,
the **low level driver** and the **application layer** — same module, three
classes:

```
user ──> Application layer (TTiPL303QMD)          "composed, user friendly"
              │  self._lowlevel
              ▼
         Low level driver (TTiPL303QMDLowLevel)   "one method ≈ one SCPI command"
              │  inherits
              ▼
         VisaInstrument (core)                    "session, typed I/O, error queue"
              │  owns
              ▼
         pyvisa resource  ── or ──  SimulatedSession
```

### Low level drivers (`*LowLevel`)

- Subclass `core.instrument.VisaInstrument`.
- One method wraps one SCPI command (or query), named after what it does:
  `set_voltage`, `get_waveform_preamble`, ... The docstring states the exact
  SCPI command as documented in the manual — this is the contract.
- Methods only format/parse; no policy, no sequencing, no state. All I/O goes
  through the typed base helpers (`write`, `query`, `query_float`,
  `query_bool`, `query_binary_block`), never through the pyvisa resource
  directly — that is what makes simulation and error translation work.
- Validate arguments that would produce *silently wrong* SCPI (bad keyword,
  bad channel number) with `ValueError`. Leave range checking of numeric
  values to the instrument; `check_errors()` surfaces its complaints.

### Application layer

- Subclasses `InstrumentApplication[TheLowLevelClass]`; the constructor
  creates the low level driver (`self._lowlevel`), the base class provides
  `initialize/close/reset/idn/check_errors` passthroughs and context manager
  support.
- Composes low level calls into tasks (e.g. `save_waveform_csv` = source +
  format + preamble + data + scaling + file), applies sensible sequencing and
  calls `check_errors()` once at the end of each configure-style method.
- Keep it small and opinionated. Anything exotic stays available via
  `instrument.lowlevel`.

### How much functionality?

Deliberately little (see `instruction.md`): drivers wrap what is needed for
automated measurements. Complex interactive setup (scope triggers, alignment)
is done at the instrument. Prefer adding a low level method over growing the
application API.

## Design decisions

### Errors are exceptions, no logging

The library raises and never logs (users decide about logging). Hierarchy in
`core/exceptions.py`, everything derives from `MessknechtError`:

- `OptionStringError` — bad `option_string` (also a `ValueError`)
- `InstrumentConnectionError` / `NotInitializedError`
- `InstrumentTimeoutError` / `InstrumentIOError` — translated pyvisa errors
  (the original exception is chained as `__cause__`)
- `InstrumentCommandError` — the *instrument* reported errors (`SYSTem:ERRor?`
  queue, or `EER?` on the TTi); carries the raw messages in `.errors`
- `InstrumentDataError` — unparsable response
- `OverloadError` — DMM over-range (±9.9e37 sentinel turned into an exception)
- `SimulationError` — operation not available in simulation

API misuse (bad channel, unknown keyword) is a plain `ValueError`/`TypeError`.

### Error checking policy

Querying the error queue after every command doubles the bus traffic, so:

- application-layer configure methods call `check_errors()` **once at the end**;
- the option `error_check=true` switches the base class to check after every
  single write (debug mode);
- `check_errors()` drains `SYSTem:ERRor?` (SCPI default); the TTi driver
  overrides it with `EER?` + a code→message table, because the PL series is
  not SCPI.

### `initialize(res, reset, option_string)`

Follows the spec in `instruction.md`. Parsing lives in `core/options.py`;
unknown keys are kept and readable by drivers (`self.options`), so a driver
can define private options without touching core. `reset=True` sends
`*CLS` + `*RST` and waits with `*OPC?` — all four instruments support that.

### Simulation design

The rule from `instruction.md`: *the caller knows the expected type*. So the
typed query helpers implement the fallback — in simulation, a `query_float()`
/ `query_last_float()` that the backend does not handle returns a fixed value
plus gaussian noise (`core/simulation.py: sim_float`), `query_int`/`query_bool`
return fixed defaults, and a *plain* `query()` with no canned response raises
`SimulationError` (that part is simply not simulated).

That fallback is the whole simulation for three of the four drivers: their
`SimulationBackend` is a **generic stub that only overrides `*IDN?`** (plus, on
the DMM, one canned `CONFigure?` string). Writes are logged and ignored;
numeric reads return defaults; string readbacks (`FUNCtion?`) and setpoint
round-trips are *not* simulated. The
exception is the **scope**, whose `SimulationBackend` returns synthetic
*binary* data (a fixed ±3 V sine and a placeholder screenshot), because binary
transfers cannot fall back to a numeric default and are the most bug-prone code
worth exercising offline. `SimulatedSession.log` records all traffic — unit
tests assert on it (they verify the *commands emitted*, which is what matters),
and it is handy when debugging a script.

Simulation is intentionally a debugging aid, not a device model. Do not chase
fidelity; if simulating something is hard, raise `SimulationError` and move on.
In particular, do **not** reintroduce per-command stateful simulators to make a
round-trip assertion pass — assert on `simulation.log` instead.

### Binary transfers

IEEE-488.2 definite-length blocks are read via
`query_binary_block()` (returns raw `bytes`); interpretation (dtype, byte
order) happens in the driver, e.g. the scope requests WORD data as unsigned
little-endian and converts with numpy. Long transfers wrap themselves in
`temporary_timeout(...)`.

The 33500B arb download uses the ASCII form
(`DATA:ARBitrary <name>,v1,v2,...`) exactly as in the manual's example
program — slower than a binary block but documented and robust; typical lab
arbs (≤100 k points) download in well under the 60 s timeout used.

### Properties vs. methods

The PSU exposes setpoints as channel *properties* (`psu.ch1.voltage = 5`)
because the instrument is a plain register bank — reads and writes are cheap
and free of side effects. The other instruments use explicit methods because
their operations sequence several commands or move data.

## Adding a new driver — checklist

1. **Read the programming manual.** Extract the exact command syntax; put the
   manual into `manuals/`.
2. Create `src/messknecht/instruments/<vendor>_<model>.py` with, in this order:
   a `_<Model>Simulation(SimulationBackend)` (usually just an `IDN` override),
   `<Model>LowLevel(VisaInstrument)` and `<Model>(InstrumentApplication[...])`.
3. Set class attributes on the low level driver if needed:
   `SIMULATION_BACKEND`, `READ_TERMINATION`/`WRITE_TERMINATION`,
   `DEFAULT_TIMEOUT_MS`; override `check_errors()` for non-SCPI instruments.
4. Export the classes in `instruments/__init__.py` and `messknecht/__init__.py`
   (`__all__` is sorted — ruff enforces it).
5. Unit tests (`tests/unit/`) asserting on
   `instrument.lowlevel.simulation.log` for command formatting (not on
   simulated readback values — those are defaults, see *Simulation design*).
6. A short integration test (`tests/integration/test_<x>_lab.py`) following the
   existing pattern: fixture via `integration_resource(request, "--<opt>")`,
   printouts for the human in the lab, safe teardown (outputs off).
7. An example script in `examples/` and a section in `docs/user-guide.md`.

## Testing

- **Integration >> unit** (see `instruction.md`): the integration tests are
  short lab scripts a human confirms at the bench. They *skip* unless a
  resource is passed:

  ```bash
  hatch run test tests/integration --psu "ASRL/dev/ttyACM0::INSTR" -s
  ```

- Unit tests cover parsing, command formatting and driver logic against the
  simulation — fast, no hardware, run in CI: `hatch run test`.

- **The split:** anything checkable without an instrument belongs in a unit
  test; a lab test answers "does this work as intended?" on real hardware.
  Never add a simulation branch (`if instrument.is_simulated: ...`) to a lab
  test — it makes the test pass while asserting nothing. If an assertion needs
  hardware, let it need hardware.

- Because lab tests and examples never run in CI, `hatch run type` includes
  `tests/` and `examples/`: mypy is what catches a misspelled driver method or
  keyword argument in them before you are standing at the bench.

## Tooling

| Command | Purpose |
|---|---|
| `hatch run test` | pytest (unit + auto-skipping integration) |
| `hatch run style` | ruff lint (rule set in `pyproject.toml`) |
| `hatch run type` | mypy on `src/`, `tests/` and `examples/` |
| `hatch run fix` | pre-commit incl. ruff autofix |

Style rules worth knowing (ruff enforces them): `from __future__ import
annotations` in every file, exception messages assigned to a variable before
raising (`EM101/102`), typing-only imports inside `if TYPE_CHECKING:`, sorted
`__all__`, no relative parent imports.
