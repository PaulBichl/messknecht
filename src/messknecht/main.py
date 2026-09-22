"""Command line entry point: list the VISA resources visible on this machine.

Run with ``python -m messknecht``. Handy to find the resource string of a
newly connected instrument.
"""

from __future__ import annotations

import sys

import pyvisa

from messknecht import __version__


def main() -> int:
    """List available VISA resources; return a process exit code."""
    print(f"messknecht {__version__}")
    try:
        manager = pyvisa.ResourceManager()
        resources = manager.list_resources()
    except Exception as exc:  # pyvisa raises various types if no backend is usable
        print(f"Could not query VISA resources: {exc}")
        print("Install a VISA backend (Keysight/NI VISA) or 'pip install pyvisa-py'.")
        return 1
    if not resources:
        print("No VISA resources found.")
        return 0
    print("Available VISA resources:")
    for resource in resources:
        print(f"  {resource}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
