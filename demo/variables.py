# demo/variables.py
# Module-level constants and configuration for the drawing library.
# Exercises: annotated variables, unannotated variables (inferred types),
#            private variables, __all__ filtering.
from __future__ import annotations

from typing import Final

from demo import types

__all__ = [
    "DEFAULT_CANVAS_WIDTH",
    "DEFAULT_CANVAS_HEIGHT",
    "DEFAULT_FILL",
    "DEFAULT_STROKE",
    "DEFAULT_STROKE_WIDTH",
    "DEFAULT_OPACITY",
    "DEFAULT_FONT_SIZE",
    "SUPPORTED_FORMATS",
    "VERSION",
    "VALUE"
]

# ---------------------------------------------------------------------------
# Public constants (in __all__)
# ---------------------------------------------------------------------------

DEFAULT_CANVAS_WIDTH:  types.Length = 800
DEFAULT_CANVAS_HEIGHT: types.Length = 600

DEFAULT_FILL:         types.Color  = "black"
DEFAULT_STROKE:       types.Color  = "none"
DEFAULT_STROKE_WIDTH: types.Length = 1

DEFAULT_OPACITY:   float = 1.0
DEFAULT_FONT_SIZE: int   = 16

SUPPORTED_FORMATS: list[str]  = ["svg", "png", "pdf"]

# Unannotated — type should be inferred as str from runtime value
VERSION = "1.0.0"
VALUE = 0

# ---------------------------------------------------------------------------
# Private constants (not in __all__ — hidden by default, shown with
# --include-private)
# ---------------------------------------------------------------------------

_INTERNAL_DPI:     int         = 96
_MAX_CHILDREN:     int         = 10_000
_DEFAULT_ENCODING: str         = "utf-8"
_debug_rendering:  bool        = False
_render_cache:     dict        = {}
