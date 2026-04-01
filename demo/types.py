# demo/types.py
# Shared type aliases and simple value types for the drawing library.
# Uses TypeAlias annotations (PEP 613) so that stub generators can detect
# and re-emit these declarations correctly.
from typing import Literal, Sequence, Tuple, TypeAlias, Union

# ---------------------------------------------------------------------------
# Numeric primitives
# ---------------------------------------------------------------------------

Number: TypeAlias = int | float
Coordinate: TypeAlias = Tuple[float, float]                       # (x, y) pair
BoundingBox: TypeAlias = Tuple[float, float, float, float]        # (x, y, w, h)

# ---------------------------------------------------------------------------
# Visual properties
# ---------------------------------------------------------------------------

#: Accepts a CSS hex string, an RGB triple, or an RGBA quadruple.
Color: TypeAlias = Union[str, Tuple[float, float, float], Tuple[float, float, float, float]]

#: Any value usable as a CSS length: px, %, "auto", or a raw number.
Length: TypeAlias = Union[str, float, int]

#: Dash pattern: a CSS string ("4 2") or a sequence of on/off lengths.
DashArray: TypeAlias = Union[str, Sequence[Number]]

# ---------------------------------------------------------------------------
# Enumerated string literals
# ---------------------------------------------------------------------------

StrokeLineCap = Literal["butt", "round", "square"]
StrokeLineJoin: TypeAlias = Literal["miter", "round", "bevel"]
FontWeight:     TypeAlias = Literal["normal", "bold", "lighter", "bolder"]
TextAnchor:     TypeAlias = Literal["start", "middle", "end"]
BlendMode:      TypeAlias = Literal["normal", "multiply", "screen", "overlay", "darken", "lighten"]
