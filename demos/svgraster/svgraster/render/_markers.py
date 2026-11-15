"""Markers: vertex orientation and ``marker`` element rendering."""
from __future__ import annotations

import math

import numpy as np

from ..dom.node import Node
from ..dom.transform import Matrix
from ..dom.units import parse_length
from ..parse.flatten import flatten_arc
from ..parse.pathdata import Path
from ..parse.viewport import parse_aspect_ratio, parse_viewbox, viewbox_transform
from ..raster import composite
from ._geometry import MARKABLE, BBox

DEFAULT_MARKER_SIZE = "3"
CLIPPING_OVERFLOW = frozenset({"hidden", "scroll", "auto"})
MARKER_TOLERANCE = 0.1


def _nonzero(*vectors):
    for v in vectors:
        if v[0] != 0 or v[1] != 0:
            return v
    return None


def _segment_directions(seg: tuple, cur: tuple[float, float]):
    kind = seg[0]
    cx, cy = cur
    if kind == "L":
        d = (seg[1] - cx, seg[2] - cy)
        return _nonzero(d), _nonzero(d), (seg[1], seg[2])
    if kind == "C":
        c1, c2, p = seg[1:3], seg[3:5], seg[5:7]
        start = _nonzero((c1[0] - cx, c1[1] - cy), (c2[0] - cx, c2[1] - cy), (p[0] - cx, p[1] - cy))
        end = _nonzero((p[0] - c2[0], p[1] - c2[1]), (p[0] - c1[0], p[1] - c1[1]), (p[0] - cx, p[1] - cy))
        return start, end, p
    if kind == "Q":
        c, p = seg[1:3], seg[3:5]
        start = _nonzero((c[0] - cx, c[1] - cy), (p[0] - cx, p[1] - cy))
        end = _nonzero((p[0] - c[0], p[1] - c[1]), (p[0] - cx, p[1] - cy))
        return start, end, p
    pts = flatten_arc(cx, cy, *seg[1:], tolerance=MARKER_TOLERANCE)
    end_pt = (seg[6], seg[7])
    if len(pts) == 0:
        return None, None, end_pt
    start = _nonzero((pts[0][0] - cx, pts[0][1] - cy))
    prev = pts[-2] if len(pts) > 1 else (cx, cy)
    end = _nonzero((pts[-1][0] - prev[0], pts[-1][1] - prev[1]))
    return start, end, end_pt


def _bisect(d_in, d_out) -> float:
    if d_in is None and d_out is None:
        return 0.0
    if d_in is None:
        return math.degrees(math.atan2(d_out[1], d_out[0]))
    if d_out is None:
        return math.degrees(math.atan2(d_in[1], d_in[0]))
    a1 = math.atan2(d_in[1], d_in[0])
    a2 = math.atan2(d_out[1], d_out[0])
    diff = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    return math.degrees(a1 + diff / 2.0)


def marker_vertices(path: Path) -> list[tuple[float, float, float]]:
    """``(x, y, angle_degrees)`` for every path vertex."""
    verts: list[list] = []
    cur = start = (0.0, 0.0)
    sub_start = 0
    for seg in path.segments:
        kind = seg[0]
        if kind == "M":
            cur = start = (seg[1], seg[2])
            verts.append([cur, None, None])
            sub_start = len(verts) - 1
            continue
        if not verts:
            verts.append([cur, None, None])
            sub_start = 0
        if kind == "Z":
            d = _nonzero((start[0] - cur[0], start[1] - cur[1])) or verts[-1][1]
            verts[-1][2] = verts[-1][2] or d
            verts.append([start, d, verts[sub_start][2]])
            verts[sub_start][1] = d
            cur = start
            continue
        d_start, d_end, end = _segment_directions(seg, cur)
        verts[-1][2] = d_start
        verts.append([end, d_end, None])
        cur = end
    return [(p[0], p[1], _bisect(d_in, d_out)) for p, d_in, d_out in verts]


def draw_markers(drawer, node: Node, path: Path, target: np.ndarray, ctm: Matrix, viewport) -> None:
    """Draw ``marker-start``/``-mid``/``-end`` for a path-like element."""
    if node.tag not in MARKABLE:
        return
    refs = [node.style.get(k, "none") for k in ("marker-start", "marker-mid", "marker-end")]
    if all(r == "none" for r in refs):
        return
    markers = [drawer.document.lookup(r, "marker") if r != "none" else None for r in refs]
    verts = marker_vertices(path)
    stroke_width = parse_length(node.style.get("stroke-width"), node.units(viewport), "xy", 1.0)
    last = len(verts) - 1
    for i, (x, y, angle) in enumerate(verts):
        kinds = [k for k, hit in ((0, i == 0), (1, 0 < i < last), (2, i == last)) if hit]
        for k in kinds:
            if markers[k] is not None:
                _draw_marker(drawer, markers[k], target, ctm, x, y, angle, stroke_width, k == 0, viewport)


def _draw_marker(drawer, marker: Node, target, ctm: Matrix, x, y, angle, stroke_width, is_start, viewport):
    units = marker.units(viewport)
    mw = parse_length(marker.get("markerWidth", DEFAULT_MARKER_SIZE), units, "x")
    mh = parse_length(marker.get("markerHeight", DEFAULT_MARKER_SIZE), units, "y")
    if mw <= 0 or mh <= 0:
        return
    orient = marker.get("orient", "0").strip()
    if orient == "auto":
        rotation = angle
    elif orient == "auto-start-reverse":
        rotation = angle + (180.0 if is_start else 0.0)
    else:
        try:
            rotation = float(orient.removesuffix("deg"))
        except ValueError:
            rotation = 0.0
    scale = stroke_width if marker.get("markerUnits", "strokeWidth") == "strokeWidth" else 1.0
    box = parse_viewbox(marker.get("viewBox"))
    vbt = viewbox_transform(box, mw, mh, parse_aspect_ratio(marker.get("preserveAspectRatio"))) if box else Matrix()
    ref = vbt.apply(parse_length(marker.get("refX"), units, "x"), parse_length(marker.get("refY"), units, "y"))
    base = (ctm @ Matrix.translate(x, y) @ Matrix.rotate(rotation) @ Matrix.scale(scale)
            @ Matrix.translate(-ref[0], -ref[1]))
    inner = (box.width, box.height) if box else (mw, mh)
    layer = np.zeros_like(target)
    drawer.draw_children(marker, layer, base @ vbt, inner)
    if marker.specified.get("overflow", "hidden") in CLIPPING_OVERFLOW:
        layer *= drawer.rect_coverage(BBox(0.0, 0.0, mw, mh), base, target.shape[:2])[..., None]
    composite.over(target, layer)
