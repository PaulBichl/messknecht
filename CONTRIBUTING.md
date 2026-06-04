# Contributing

## Setup

```bash
# Create development environment
hatch env create

# Install pre-commit hooks
hatch run fix install
```

## Development

```bash
# Type checking
hatch run type

# Code style check & fix
hatch run style
hatch run fix

# Run tests
hatch run test

# Test with coverage
hatch run test --cov=src
```

## Code Style

- Use type hints for all functions
- Write docstrings for public functions
- Use descriptive variable names
- Keep functions small and focused

Example:
```python
from __future__ import annotations

def process_data(items: list[str]) -> dict[str, int]:
    """Process items and return count by length."""
    return {item: len(item) for item in items}
```

## Testing

- Place unit tests in `tests/unit/`
- Use descriptive test names: `test_function_name_case`
- Add tests for new features

## Before Committing

```bash
hatch run type
hatch run style
hatch run fix --all-files
hatch run test
```

---

Thanks for contributing!
