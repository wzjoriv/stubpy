"""Element geometry: shapes to paths, bounding boxes and units."""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from ..dom.node import Node
from ..dom.transform import IDENTITY, Matrix, parse_transform
from ..dom.units import parse_length, parse_numbers
from ..parse.flatten import flatten_path, polylines_bbox
from ..parse.pathdata import Path, parse_path
from ..parse.shapes import circle_path, ellipse_path, line_path, poly_path, rect_path
from ..parse.viewport import parse_aspect_ratio, parse_viewbox, viewbox_transform

SHAPES = frozenset({"rect", "circle", "ellipse", "line", "polyline", "polygon", "path"})
CONTAINERS = frozenset({"g", "a", "switch", "svg"})
MARKABLE = frozenset({"path", "line", "polyline", "polygon"})
BBOX_TOLERANCE = 0.05
AUTO = "auto"


class BBox(NamedTuple):
    """An axis-aligned box ``(x, y, width, height)``."""

    x: float
    y: float
    width: float
    height: float

    @property
    def is_empty(self) -> bool:
        """Whether width or height is zero."""
        return self.width <= 0 or self.height <= 0

    def matrix(self) -> Matrix:
        """Maps the unit square onto the box."""
        return Matrix(self.width, 0.0, 0.0, self.height, self.x, self.y)

    @classmethod
    def from_bounds(cls, bounds: tuple[float, float, float, float]) -> BBox:
        """From ``(x0, y0, x1, y1)``."""
        x0, y0, x1, y1 = bounds
        return cls(x0, y0, x1 - x0, y1 - y0)


def length(node: Node, name: str, viewport: tuple[float, float], axis: str = "x", default: float = 0.0) -> float:
    """An attribute length in user units."""
    return parse_length(node.get(name), node.units(viewport), axis, default)


def node_transform(node: Node) -> Matrix:
    """The element's ``transform`` attribute."""
    return parse_transform(node.get("transform"))


def shape_path(node: Node, viewport: tuple[float, float]) -> Path:
    """The geometry of a basic shape or ``path`` element."""
    tag = node.tag
    if tag == "path":
        return parse_path(node.get("d", ""))
    if tag == "rect":
        rx_raw, ry_raw = node.get("rx"), node.get("ry")
        rx = length(node, "rx", viewport, "x") if rx_raw not in (None, AUTO) else None
        ry = length(node, "ry", viewport, "y") if ry_raw not in (None, AUTO) else None
        rx = ry if rx is None else rx
        ry = rx if ry is None else ry
        return rect_path(length(node, "x", viewport, "x"), length(node, "y", viewport, "y"),
                         length(node, "width", viewport, "x"), length(node, "height", viewport, "y"),
                         max(rx or 0.0, 0.0), max(ry or 0.0, 0.0))
    if tag == "circle":
        return circle_path(length(node, "cx", viewport, "x"), length(node, "cy", viewport, "y"),
                           length(node, "r", viewport, "xy"))
    if tag == "ellipse":
        return ellipse_path(length(node, "cx", viewport, "x"), length(node, "cy", viewport, "y"),
                            length(node, "rx", viewport, "x"), length(node, "ry", viewport, "y"))
    if tag == "line":
        return line_path(length(node, "x1", viewport, "x"), length(node, "y1", viewport, "y"),
                         length(node, "x2", viewport, "x"), length(node, "y2", viewport, "y"))
    if tag in ("polyline", "polygon"):
        return poly_path(parse_numbers(node.get("points")), tag == "polygon")
    return Path()


def nested_viewport(node: Node, viewport: tuple[float, float],
                    size: tuple[float | None, float | None] = (None, None)) -> tuple[Matrix, tuple[float, float],
                                                                                         BBox]:
    """Transform, new viewport size and clip rectangle for ``svg``/``symbol``."""
    x = length(node, "x", viewport, "x")
    y = length(node, "y", viewport, "y")
    w = size[0] if size[0] is not None else length(node, "width", viewport, "x", viewport[0])
    h = size[1] if size[1] is not None else length(node, "height", viewport, "y", viewport[1])
    if node.get("width") is None and size[0] is None and node.tag == "svg":
        w = viewport[0]
    box = parse_viewbox(node.get("viewBox"))
    m = Matrix.translate(x, y)
    if box is not None and w > 0 and h > 0:
        m = m @ viewbox_transform(box, w, h, parse_aspect_ratio(node.get("preserveAspectRatio")))
        inner = (box.width, box.height)
    else:
        inner = (w, h)
    return m, inner, BBox(x, y, w, h)


def union(a: tuple | None, b: tuple | None) -> tuple | None:
    """Union of two ``(x0, y0, x1, y1)`` bounds."""
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _transformed_bounds(bounds, m: Matrix):
    if bounds is None:
        return None
    x0, y0, x1, y1 = bounds
    return m.transform_rect(x0, y0, x1 - x0, y1 - y0)


def node_bounds(node: Node, viewport: tuple[float, float], document=None, depth: int = 0) -> tuple | None:
    """``(x0, y0, x1, y1)`` of ``node``'s geometry in its own user space."""
    if node.style.get("display") == "none" or depth > 32:
        return None
    if node.tag in SHAPES:
        return polylines_bbox(flatten_path(shape_path(node, viewport), BBOX_TOLERANCE))
    if node.tag == "image":
        w, h = length(node, "width", viewport, "x"), length(node, "height", viewport, "y")
        if w <= 0 or h <= 0:
            return None
        x, y = length(node, "x", viewport, "x"), length(node, "y", viewport, "y")
        return (x, y, x + w, y + h)
    if node.tag == "text":
        from .text import text_bounds
        return text_bounds(node, viewport, document)
    if node.tag == "use" and document is not None:
        target = document.lookup(node.href)
        if target is None:
            return None
        offset = Matrix.translate(length(node, "x", viewport, "x"), length(node, "y", viewport, "y"))
        if target.tag in ("symbol", "svg"):
            m, inner, _ = nested_viewport(target, viewport, (_opt_len(node, "width", viewport, "x"),
                                                              _opt_len(node, "height", viewport, "y")))
            inner_bounds = None
            for child in target.children:
                inner_bounds = union(inner_bounds, _transformed_bounds(
                    node_bounds(child, inner, document, depth + 1), node_transform(child)))
            return _transformed_bounds(inner_bounds, offset @ m)
        return _transformed_bounds(node_bounds(target, viewport, document, depth + 1),
                                   offset @ node_transform(target))
    if node.tag in CONTAINERS:
        inner_vp, m = viewport, IDENTITY
        if node.tag == "svg" and node.parent is not None:
            m, inner_vp, _ = nested_viewport(node, viewport)
        result = None
        for child in node.children:
            result = union(result, _transformed_bounds(
                node_bounds(child, inner_vp, document, depth + 1), node_transform(child)))
        return _transformed_bounds(result, m)
    return None


def _opt_len(node: Node, name: str, viewport, axis: str) -> float | None:
    return length(node, name, viewport, axis) if node.get(name) is not None else None


def node_bbox(node: Node, viewport: tuple[float, float], document=None) -> BBox | None:
    """The object bounding box, or ``None`` when the element has no geometry."""
    bounds = node_bounds(node, viewport, document)
    return BBox.from_bounds(bounds) if bounds is not None else None


def device_polygons(polylines, m: Matrix, dx: float = 0.0, dy: float = 0.0) -> list[np.ndarray]:
    """Transform polyline points to device space, shifted by ``(-dx, -dy)``."""
    shift = Matrix.translate(-dx, -dy) @ m
    return [shift.apply_points(p.points if hasattr(p, "points") else p) for p in polylines]
