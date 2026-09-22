# messknecht

Lab automation: Python instrument drivers on top of [pyvisa](https://pyvisa.readthedocs.io/).

Supported instruments:

- **TTi PL303QMD** — dual output DC power supply
- **Keysight InfiniiVision DSO-X 3014T** — oscilloscope (waveform → CSV, screenshots)
- **Keysight 33500B** — waveform generator (standard waveforms, arbs from CSV)
- **Keysight 34450A** — digital multimeter (DC voltage focus, continuous/triggered)

## Features

- Uniform lifecycle: `initialize(resource, reset, option_string)` on every driver
- Two layers per instrument: a user friendly application layer plus a thin,
  fully accessible low level SCPI wrapper
- Errors are exceptions (`MessknechtError` hierarchy) — no hidden logging
- Built-in simulation mode (`simulate=true`) to develop scripts without hardware

## Installation

```bash
pip install .
```

plus a VISA backend (Keysight IO Libraries / NI-VISA, or `pip install pyvisa-py`).

For development:

```bash
pip install -e ".[dev]"
pre-commit install
```

## Quick Start

```bash
python -m messknecht          # list VISA resources to find your instrument
```

```python
from messknecht import TTiPL303QMD

with TTiPL303QMD() as psu:
    psu.initialize("ASRL/dev/ttyACM0::INSTR", reset=True)
    psu.ch1.configure(voltage=5.0, current_limit=0.1)
    psu.ch1.output = True
    print(psu.ch1.measured_voltage)
```

No hardware at hand? Every driver also runs in simulation:

```python
psu.initialize("SIM::psu", True, "simulate=true")
```

More: [user guide](./docs/user-guide.md) and runnable [examples](./examples)
for the scope, waveform generator and DMM.

## Development

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the workflow and the
[developer guide](./docs/developer-guide.md) for architecture and how to add
a new instrument driver.

### Commands

- `hatch run test` - Run tests (unit + integration*)
- `hatch run type` - Type checking
- `hatch run style` - Lint check
- `hatch run fix` - Auto-fix code style
- `hatch run update-precommit` - Update pre-commit hooks

*Integration tests are short lab scripts that need real instruments:

```bash
hatch run test tests/integration --psu "ASRL/dev/ttyACM0::INSTR" -s
```

## Documentation

See the [`docs/`](./docs) directory: [user guide](./docs/user-guide.md),
[developer guide](./docs/developer-guide.md). Instrument programming manuals
are in [`manuals/`](./manuals).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT — see the [LICENSE](./LICENSE) file.
