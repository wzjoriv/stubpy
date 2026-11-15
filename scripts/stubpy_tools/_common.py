"""Paths and helpers shared by stubpy's developer commands."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["ROOT", "DEMO", "DEMO_STUBS", "RASTER", "BUILD", "use_local_stubpy"]

#: The repository root (``scripts/stubpy_tools/_common.py`` → two folders up from ``scripts``)
ROOT = Path(__file__).resolve().parents[2]
#: The svgwriter corpus the integration tests stub
DEMO = ROOT / "demos" / "svgwriter" / "svgwriter"
#: The svgraster demo whose compiled extensions ``dev.py stubpy raster`` stubs
RASTER = ROOT / "demos" / "svgraster" / "svgraster"
#: Scratch output of the developer commands (git-ignored)
BUILD = ROOT / "build" / "dev"
#: Where ``dev.py stubpy demo`` writes the corpus stubs
DEMO_STUBS = BUILD / "svgwriter-stubs"


def use_local_stubpy() -> None:
    """Import ``stubpy`` from this checkout, even when another copy is installed."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
