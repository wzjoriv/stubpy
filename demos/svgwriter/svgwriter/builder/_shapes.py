"""Composite shapes registered by name for the CLI and plugins."""

from __future__ import annotations

import functools
import math
from collections.abc import Callable
from typing import Any, Final, TypeVar

from .._internal._registry import Registry
from .._internal._typing import P
from ..elements.base import Element
from ..elements.shapes import Path, Polygon
from ..path.builder import PathBuilder

__all__ = ["SHAPES", "arrow", "gear", "regular_polygon", "shape_factory", "star"]

E = TypeVar("E", bound=Element)

SHAPES: Final[Registry[Callable[..., Element]]] = Registry("shape")
FULL_TURN: Final = 360.0
QUARTER_TURN: Final = 90.0
DEFAULT_STAR_POINTS: Final = 5
DEFAULT_INNER_RATIO: Final = 0.5
DEFAULT_HEAD_SIZE: Final = 10.0
ARROW_HEAD_ANGLE: Final = 30.0
DEFAULT_TEETH: Final = 12
TOOTH_DEPTH_RATIO: Final = 0.15


def shape_factory(name: str) -> Callable[[Callable[P, E]], Callable[P, E]]:
    """Register a function returning an element under *name*.

    The wrapper checks the return type, so plugins fail loudly.
    """

    def decorate(func: Callable[P, E]) -> Callable[P, E]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> E:
            result = func(*args, **kwargs)
            if not isinstance(result, Element):
                raise TypeError(f"shape {name!r} returned {type(result).__name__}")
            return result

        SHAPES.add(name, wrapper)
        return wrapper

    return decorate


def _ring(cx: float, cy: float, radii: list[float], rotation: float) -> list[tuple[float, float]]:
    count = len(radii)
    points = []
    for index, radius in enumerate(radii):
        angle = math.radians(rotation + FULL_TURN * index / count)
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


@shape_factory("star")
def star(
    cx: float,
    cy: float,
    outer: float,
    inner: float | None = None,
    points: int = DEFAULT_STAR_POINTS,
    **kwargs: Any,
) -> Polygon:
    """A star polygon with *points* tips, pointing up."""
    inner = outer * DEFAULT_INNER_RATIO if inner is None else inner
    return Polygon(_ring(cx, cy, [outer, inner] * points, -QUARTER_TURN), **kwargs)


@shape_factory("polygon")
def regular_polygon(cx: float, cy: float, radius: float, sides: int = 6, **kwargs: Any) -> Polygon:
    """A regular polygon with one vertex pointing up."""
    return Polygon(_ring(cx, cy, [radius] * sides, -QUARTER_TURN), **kwargs)


@shape_factory("gear")
def gear(cx: float, cy: float, radius: float, teeth: int = DEFAULT_TEETH, **kwargs: Any) -> Polygon:
    """A gear outline with square-ish teeth."""
    depth = radius * TOOTH_DEPTH_RATIO
    radii = [radius, radius, radius - depth, radius - depth] * teeth
    return Polygon(_ring(cx, cy, radii, 0.0), **kwargs)


@shape_factory("arrow")
def arrow(x1: float, y1: float, x2: float, y2: float, head: float = DEFAULT_HEAD_SIZE, **kwargs: Any) -> Path:
    """A line with an open arrowhead at ``(x2, y2)``."""
    angle = math.atan2(y2 - y1, x2 - x1)
    spread = math.radians(ARROW_HEAD_ANGLE)
    builder = PathBuilder().move_to(x1, y1).line_to(x2, y2)
    for side in (-1, 1):
        a = angle + math.pi + side * spread
        builder.move_to(x2 + head * math.cos(a), y2 + head * math.sin(a)).line_to(x2, y2)
    kwargs.setdefault("fill", "none")
    return Path(builder, **kwargs)
