# Agent Instructions

Guide for Claude, Copilot, and other AI assistants on code style and project patterns.

## Project Setup

- **Language**: Python 3.12+
- **Package Manager**: Hatch with uv
- **Code Quality**: Ruff (lint/format) + Mypy (type checking) + Pre-commit
- **Testing**: Pytest

## Code Patterns

### Imports

Always start with `from __future__ import annotations`. Keep imports organized:

```python
from __future__ import annotations

import os
import sys
from typing import Any

import requests

from messknecht.module import MyClass
from messknecht.utils import helper
```

### Type Hints

Always use type hints:

```python
def process_data(data: list[str], count: int) -> dict[str, int]:
    """Process data and return results."""
    return {item: len(item) for item in data}

class DataProcessor:
    def __init__(self, name: str) -> None:
        self.name = name

    def analyze(self, values: list[float]) -> float:
        """Calculate average of values."""
        return sum(values) / len(values) if values else 0.0
```

### Docstrings

Use brief docstrings. Add Args/Returns for complex functions:

```python
def simple(x: int) -> int:
    """Return x squared."""
    return x * x

def complex_func(data: list[dict[str, Any]], threshold: float) -> dict[str, list[int]]:
    """Filter and group data by category.

    Args:
        data: List of dicts with 'category' and 'value'
        threshold: Minimum value to include

    Returns:
        Mapping of category to filtered values
    """
    result = {}
    for item in data:
        cat = item.get("category", "other")
        val = item.get("value", 0)
        if val >= threshold:
            if cat not in result:
                result[cat] = []
            result[cat].append(val)
    return result
```

### Error Handling

Be specific with exceptions:

```python
def load_file(path: str) -> str:
    """Load file contents."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    try:
        with open(path) as f:
            return f.read()
    except IOError as e:
        raise RuntimeError(f"Cannot read {path}: {e}") from e
```

## Project Structure

```
messknecht/
├── __init__.py          # Package init
├── main.py              # Main entry point
└── module.py            # Add modules here

tests/
├── conftest.py          # Pytest fixtures
├── unit/                # Unit tests
└── integration/         # Integration tests (optional)
```

## Testing

### Unit Tests

```python
def test_simple() -> None:
    """Test basic functionality."""
    result = process_data(["hello"])
    assert result == {"hello": 5}

@pytest.mark.parametrize("input_val,expected", [
    ("a", 1),
    ("hello", 5),
])
def test_lengths(input_val: str, expected: int) -> None:
    """Test various inputs."""
    assert len(input_val) == expected
```

### With Fixtures

```python
# In conftest.py
import pytest

@pytest.fixture
def sample_data() -> list[int]:
    return [1, 2, 3, 4, 5]

# In test file
def test_with_fixture(sample_data: list[int]) -> None:
    assert len(sample_data) == 5
```

## Commands

| Command | Purpose |
|---------|---------|
| `hatch run type` | Type checking (mypy) |
| `hatch run style` | Lint check (ruff) |
| `hatch run fix` | Auto-fix style & run pre-commit |
| `hatch run test` | Run tests (pytest) |
| `hatch run test --cov=src` | Run with coverage |

## Naming Conventions

- **Modules**: `snake_case` (e.g., `data_processor.py`)
- **Classes**: `PascalCase` (e.g., `DataProcessor`)
- **Functions**: `snake_case` (e.g., `process_data()`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_ITEMS = 100`)
- **Private**: Prefix with `_` (e.g., `_internal_method()`)

## Do's and Don'ts

### ✅ Do

- Use type hints everywhere
- Write docstrings for public APIs
- Keep functions small and focused
- Add tests for new features
- Use descriptive names
- Catch specific exceptions

### ❌ Don't

- Use relative imports (use absolute imports)
- Bare `except:` clauses (catch specific exceptions)
- Leave unused imports (Ruff will flag these)
- Use magic numbers (use named constants)
- Create deeply nested code (extract to functions)

---

Look at `main.py` for basic structure and `pyproject.toml` for tool configuration.
