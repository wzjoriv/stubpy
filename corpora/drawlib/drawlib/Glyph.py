"""A module named after its main class, as Pillow's ``Image`` module holds ``Image``."""
from __future__ import annotations


class Glyph:
    """One drawable character."""

    def advance(self) -> float:
        return 0.0
