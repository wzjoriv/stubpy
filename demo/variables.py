# demo/variables.py
# Exercises module-level variable stub generation (P2-B)
# Covers: annotated vars, unannotated vars, TypeAlias, TypeVar
from __future__ import annotations

from typing import TypeVar, Optional

__all__ = [
    "MAX_SIZE",
    "DEFAULT_NAME",
    "VERSION",
    "PI",
    "ENABLED",
]

# Annotated variables
MAX_SIZE: int = 1024
DEFAULT_NAME: str = "default"
PI: float = 3.14159
ENABLED: bool = True

# Unannotated variable — type should be inferred from runtime value
VERSION = "1.0.0"

# Private — should NOT appear in stubs (unless --include-private)
_INTERNAL_CACHE: dict = {}
_debug_mode = False
