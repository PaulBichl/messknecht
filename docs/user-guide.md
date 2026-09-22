# User Guide

messknecht is a small instrument driver library on top of [pyvisa](https://pyvisa.readthedocs.io/).
It currently drives:

| Instrument | Class | Highlights |
|---|---|---|
| TTi PL303QMD (dual PSU) | `TTiPL303QMD` | channel properties, output on/off, protection |
| Keysight DSO-X 3014T (scope) | `KeysightDSOX3000T` | waveform → CSV, screenshots, basic setup |
| Keysight 33500B (waveform gen.) | `Keysight33500B` | standard waveforms, arbs from CSV |
| Keysight 34450A (DMM) | `Keysight34450A` | `configure.voltage_dc(...)`, continuous/triggered |

Complete runnable scripts live in [`examples/`](../examples) — they are the fastest way to get started.

## Installation

```bash
pip install .
```

You also need a VISA backend, one of:

- Keysight IO Libraries or NI-VISA (recommended in the lab), or
- the pure Python backend: `pip install pyvisa-py` (then pass `visa_library=@py`, see below).

## Finding your instrument

```bash
python -m messknecht        # lists all VISA resources visible on this machine
```

Typical resource strings: `USB0::0x2A8D::0x0396::MY58493xx::INSTR`,
`TCPIP0::192.168.1.20::INSTR`, `ASRL/dev/ttyACM0::INSTR` (serial).

## Connecting: `initialize()`

Every driver is used the same way:

```python
from messknecht import Keysight34450A

dmm = Keysight34450A()
dmm.initialize("USB0::...::INSTR", reset=True)   # reset: start from *RST defaults
...
dmm.close()
```

or with a context manager (closes automatically):

```python
with Keysight34450A() as dmm:
    dmm.initialize("USB0::...::INSTR", True)
    ...
```

### The option string

`initialize(res, reset, option_string="")` takes `key=value` pairs separated by `,` or `;`:

| Key | Example | Meaning |
|---|---|---|
| `simulate` | `simulate=true` | run against the built-in simulation (no hardware) |
| `timeout` | `timeout=10000` | VISA I/O timeout in ms (default 5000) |
| `error_check` | `error_check=true` | query the error queue after **every** write (slow, great for debugging) |
| `visa_library` | `visa_library=@py` | select the pyvisa backend (e.g. pyvisa-py) |

```python
dmm.initialize("USB0::...::INSTR", True, "timeout=10000, error_check=true")
```

## Error handling

The library raises exceptions and never logs — wrap calls in `try/except` and
log yourself if you need to. All library errors derive from
`messknecht.MessknechtError`:

```python
from messknecht import MessknechtError, InstrumentTimeoutError

try:
    value = dmm.read()
except InstrumentTimeoutError:
    print("increase the timeout or check the trigger settings")
except MessknechtError as error:
    print(f"instrument problem: {error}")
```

Invalid *arguments* (wrong channel number, unknown keyword, ...) raise plain
`ValueError` before anything is sent to the instrument.

## Power supply — TTi PL303QMD

```python
from messknecht import TTiPL303QMD

with TTiPL303QMD() as psu:
    psu.initialize("ASRL/dev/ttyACM0::INSTR", True)

    psu.ch1.configure(voltage=5.0, current_limit=0.1)   # one call ...
    psu.ch2.voltage = 12.0                              # ... or properties
    psu.ch2.current_limit = 0.5

    psu.ch1.output = True
    print(psu.ch1.measured_voltage, psu.ch1.measured_current)

    psu.output_all(False)     # both outputs off
    psu.local()               # give the front panel back to the user
```

Also available per channel: `ovp`, `ocp` (protection trip points),
`current_range` (`CurrentRange.LOW` = 500 mA range, 0.1 mA meter resolution
and 0.01 mA setting resolution; the output must be off to change it).

## Oscilloscope — Keysight DSO-X 3014T

Set up signals, trigger and resolution interactively at the scope — the driver
deliberately covers only basic setup plus data readout:

```python
from messknecht import KeysightDSOX3000T

with KeysightDSOX3000T() as scope:
    scope.initialize("USB0::...::INSTR", False)     # False: keep the scope setup!

    scope.save_waveform_csv("wave.csv", channels=[1, 2], points=2000)
    scope.screenshot("screen.png")                  # .png or .bmp

    print(scope.measure_vpp(1), scope.measure_frequency(1))
```

Notes:

- `save_waveform_csv(..., acquire=True)` (default) runs one fresh acquisition
  (`:DIGitize`) so all channels come from the same trigger; the scope is left
  stopped. Use `acquire=False` to read what is currently on screen.
- `points_mode="raw"` reads the full acquisition memory (scope must be stopped).
- `get_waveform(channel)` returns time/voltage numpy arrays if you want the
  data instead of a file.
- Basic setup helpers exist if you need them:
  `setup_channel(1, scale=0.5, coupling="dc")`, `setup_timebase(scale=1e-3)`,
  `setup_edge_trigger(source=1, level=0.5, slope="positive")`, `autoscale()`,
  `run()/stop()/single()/digitize()`.

## Waveform generator — Keysight 33500B

```python
from messknecht import Keysight33500B

with Keysight33500B() as wfg:
    wfg.initialize("TCPIP0::...::INSTR", True)

    # standard waveforms (amplitude in Vpp)
    wfg.configure_sine(frequency=1e3, amplitude=1.0, offset=0.0)
    wfg.configure_square(frequency=1e3, amplitude=1.0, duty_cycle=25.0)
    wfg.configure_ramp(frequency=100.0, amplitude=2.0, symmetry=50.0)  # triangle
    wfg.configure_dc(offset=1.5)

    wfg.set_output_load(50)        # or "INFinity" - affects the real amplitude!
    wfg.output(True)

    # arbitrary waveform from CSV (one value per line, or comma separated)
    wfg.load_arbitrary_csv("my_arb.csv", sample_rate=100e3, amplitude=1.0)
```

Arb notes: samples are normalized to −1…+1 (`normalize=False` to forbid),
8…1,000,000 points, repetition rate = `sample_rate / number_of_points`.
`load_arbitrary(values, ...)` takes a Python sequence instead of a file.

## Multimeter — Keysight 34450A

```python
from messknecht import Keysight34450A

with Keysight34450A() as dmm:
    dmm.initialize("USB0::...::INSTR", True)

    # continuous (default): every read() triggers a fresh measurement
    dmm.configure.voltage_dc(range=10, resolution=1.5e-6)
    print(dmm.read())

    # triggered: measure only on demand (BUS trigger)
    dmm.configure.voltage_dc(range=10, continuous=False)
    print(dmm.read())              # arms, software-triggers, fetches
```

- Ranges (V DC): 0.1, 1, 10, 100, 1000 or `"AUTO"`; resolutions: `3.0e-5`,
  `2.0e-5`, `1.5e-6` (5½ digits) — only together with a fixed range.
- Other functions: `configure.voltage_ac / current_dc / current_ac /
  resistance / resistance_4wire / frequency / capacitance / continuity / diode`.
- An over-range measurement raises `OverloadError` instead of returning 9.9e37.

## Simulation mode

Every driver runs without hardware when you pass `simulate=true`:

```python
psu.initialize("SIM::psu", True, "simulate=true")
```

This is a debugging aid for *script logic*, not a device model. Commands are
accepted and logged; numeric reads (`dmm.read()`, measurements, frequency, …)
return a plausible default with a little noise, and the scope produces a fixed
sine wave and placeholder screenshots. It deliberately does **not** model
device state, so setpoints do not round-trip, and most string readbacks
(e.g. `FUNCtion?`) raise `SimulationError` — the few that are simulated
(`CONFigure?`, the scope's waveform preamble) return a fixed canned response
that does not reflect what you configured.
Use it to check that a script *runs* and sends the right commands; confirm real
values on hardware.

## Low level access

Everything the application layer does not cover is available on the low level
driver, which is a thin, documented wrapper around the SCPI commands:

```python
scope.lowlevel.set_waveform_points_mode("RAW")
scope.lowlevel.write(":ACQuire:TYPE AVERage")     # raw SCPI as last resort
print(scope.lowlevel.query(":ACQuire:TYPE?"))
```

## Troubleshooting

- **`InstrumentConnectionError`** — wrong resource string or no VISA backend.
  Run `python -m messknecht` to list resources.
- **`InstrumentTimeoutError`** — the instrument needs longer than the VISA
  timeout (big transfers, slow measurements): pass `timeout=...` in the option
  string, or check that the instrument isn't waiting for a trigger.
- **Raw TCP sockets** (`TCPIP0::host::5025::SOCKET`) work; prefer `::INSTR`
  resources when available.
- **Debugging SCPI traffic**: `error_check=true` in the option string raises
  immediately on the command that the instrument rejected.
