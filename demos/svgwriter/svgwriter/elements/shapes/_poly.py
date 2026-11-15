"""``polyline`` and ``polygon``."""

from __future__ import annotations

import math
from typing import Any, ClassVar, Final

from ..._internal._typing import Points, Self
from ...path.builder import PathBuilder
from ...path.data import BBox, PathData
from ._base import Shape, parse_points

__all__ = ["Polygon", "Polyline"]

FULL_CIRCLE: Final = 360.0


class Polyline(Shape, tag="polyline"):
    """``<polyline>``: an open sequence of straight segments."""

    geometry_attributes: ClassVar[frozenset[str]] = frozenset({"points"})

    def __init__(self, points: Points | str = (), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.points = points  # type: ignore[assignment]

    @property
    def points(self) -> list[tuple[float, float]]:
        raw = self.attributes.get("points", ())
        return parse_points(raw) if isinstance(raw, str) else list(raw)

    @points.setter
    def points(self, value: Points | str) -> None:
        pairs = parse_points(value) if isinstance(value, str) else [tuple(p) for p in value]
        self.attributes["points"] = tuple(pairs)

    @classmethod
    def regular(cls, cx: float, cy: float, radius: float, sides: int, **kwargs: Any) -> Self:
        """Vertices of a regular polygon, starting at the top."""
        step = FULL_CIRCLE / sides
        pts = [
            (cx + radius * math.sin(math.radians(i * step)), cy - radius * math.cos(math.radians(i * step)))
            for i in range(sides)
        ]
        return cls(pts, **kwargs)

    @property
    def bbox(self) -> BBox:
        return BBox.from_points(self.points)

    def _builder(self) -> PathBuilder:
        builder = PathBuilder()
        for index, (x, y) in enumerate(self.points):
            if index == 0:
                builder.move_to(x, y)
            else:
                builder.line_to(x, y)
        return builder

    def local_outline(self) -> PathData:
        return self._builder().build()


class Polygon(Polyline, tag="polygon"):
    """``<polygon>``: a closed ``Polyline``."""

    @property
    def area(self) -> float:
        """Signed-area magnitude (shoelace formula)."""
        pts = self.points
        total = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
        return abs(total) / 2.0

    def local_outline(self) -> PathData:
        builder = self._builder()
        return builder.close().build() if len(builder) else builder.build()
