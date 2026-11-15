"""The ``MISSING`` sentinel for "argument not supplied"."""

from __future__ import annotations

import enum
from typing import Final, Literal

__all__ = ["MISSING", "MissingType"]


class MissingType(enum.Enum):
    """Single-member enum so the sentinel has a precise type."""

    MISSING = enum.auto()

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> Literal[False]:
        return False


MISSING: Final = MissingType.MISSING
