# demo/types.py — mirrors the structure of phig/types.py
from typing import Literal, Sequence, Tuple, Union

Number = int | float
Length = str | float | int
Color  = str | Tuple[float, float, float] | Tuple[float, float, float, float]

StrokeLineCap  = Literal["butt", "round", "square"]
StrokeLineJoin = Literal["miter", "round", "bevel"]
DashArray      = Union[str, Sequence[Number]]