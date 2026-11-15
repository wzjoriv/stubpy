"""Command line entry point: ``python -m svgraster``."""
from __future__ import annotations

import sys

from .cli import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    sys.exit(main())
