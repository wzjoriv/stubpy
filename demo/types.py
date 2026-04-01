# demo/types.py
# Shared type aliases and simple value types for the drawing library.
from typing import Literal, Sequence, Tuple, Union

# ---------------------------------------------------------------------------
# Numeric primitives
# ---------------------------------------------------------------------------

Number = int | float
Coordinate = Tuple[float, float]                       # (x, y) pair
BoundingBox = Tuple[float, float, float, float]        # (x, y, w, h)

# ---------------------------------------------------------------------------
# Visual properties
# ---------------------------------------------------------------------------

#: Accepts a CSS hex string, an RGB triple, or an RGBA quadruple.
Color = Union[str, Tuple[float, float, float], Tuple[float, float, float, float]]

#: Any value usable as a CSS length: px, %, "auto", or a raw number.
Length = Union[str, float, int]

#: Dash pattern: a CSS string ("4 2") or a sequence of on/off lengths.
DashArray = Union[str, Sequence[Number]]

# ---------------------------------------------------------------------------
# Enumerated string literals
# ---------------------------------------------------------------------------

StrokeLineCap  = Literal["butt", "round", "square"]
StrokeLineJoin = Literal["miter", "round", "bevel"]
FontWeight     = Literal["normal", "bold", "lighter", "bolder"]
TextAnchor     = Literal["start", "middle", "end"]
BlendMode      = Literal["normal", "multiply", "screen", "overlay", "darken", "lighten"]
