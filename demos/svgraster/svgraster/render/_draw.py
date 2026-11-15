"""The tree walker that paints elements onto premultiplied RGBA layers."""
from __future__ import annotations

import math

import numpy as np

from ..dom.node import Node
from ..dom.transform import Matrix
from ..dom.units import parse_fraction, parse_length, parse_length_list
from ..parse.flatten import flatten_path, polylines_bbox
from ..raster import composite, scanline
from ..raster.stroke import stroke_polylines
from ._effects import Effects
from ._filtering import FilterEngine
from ._geometry import SHAPES, BBox, length, nested_viewport, node_bbox, node_transform, shape_path
from ._markers import draw_markers
from ._servers import PaintServers
from ._text import layout

NON_RENDERED = frozenset({
    "defs", "clipPath", "mask", "marker", "pattern", "linearGradient", "radialGradient",
    "symbol", "filter", "style", "title", "desc", "metadata", "stop", "script", "font",
    "foreignObject", "image", "view", "cursor",
})
CLIPPING_OVERFLOW = frozenset({"hidden", "scroll", "auto"})
MAX_DEPTH = 64
TEXT_STROKE_JOIN = "round"


def _unit(value: float) -> float:
    return min(1.0, max(0.0, value))


class Drawer:
    """Renders a :class:`~svgraster.dom.Document` subtree onto float32 layers."""

    def __init__(self, document, samples: int = scanline.DEFAULT_SAMPLES, tolerance: float = 0.1):
        self.document = document
        self.samples = samples
        self.tolerance = tolerance
        self.servers = PaintServers(self)
        self.effects = Effects(self)
        self.filters = FilterEngine(self)
        self._depth = 0
        self._active_refs: set[int] = set()

    def draw_children(self, node: Node, canvas: np.ndarray, ctm: Matrix, viewport) -> None:
        """Draw the children of ``node`` (only the first rendered one for ``switch``)."""
        for child in node.children:
            self.draw(child, canvas, ctm, viewport)
            if node.tag == "switch" and child.tag not in NON_RENDERED:
                break

    def draw(self, node: Node, canvas: np.ndarray, ctm: Matrix, viewport) -> None:
        """Draw one element and its descendants onto ``canvas``."""
        if node.tag in NON_RENDERED or node.style.get("display") == "none" or self._depth > MAX_DEPTH:
            return
        local = ctm @ node_transform(node)
        if not local.is_invertible:
            return
        style = node.style
        opacity = _unit(parse_fraction(style.get("opacity"), 1.0))
        if opacity <= 0.0:
            return
        doc = self.document
        clip = doc.lookup(style.get("clip-path"), "clipPath") if style.get("clip-path") != "none" else None
        mask = doc.lookup(style.get("mask"), "mask") if style.get("mask") != "none" else None
        filt = doc.lookup(style.get("filter"), "filter") if style.get("filter") != "none" else None
        layered = opacity < 1.0 or clip is not None or mask is not None or filt is not None
        target = np.zeros_like(canvas) if layered else canvas
        self._depth += 1
        try:
            self._content(node, target, local, viewport)
        finally:
            self._depth -= 1
        if not layered:
            return
        bbox = node_bbox(node, viewport, doc)
        if filt is not None:
            target = self.filters.apply(filt, target, local, bbox, viewport)
            if target is None:
                return
        if clip is not None:
            target *= self.effects.clip_coverage(clip, local, bbox, target.shape[:2], viewport)[..., None]
        if mask is not None:
            self.effects.apply_mask(mask, target, local, bbox, viewport)
        composite.over(canvas, target, opacity)

    def _content(self, node: Node, target: np.ndarray, ctm: Matrix, viewport) -> None:
        tag = node.tag
        if tag in SHAPES:
            self.draw_shape(node, target, ctm, viewport)
        elif tag == "text":
            self.draw_text(node, target, ctm, viewport)
        elif tag == "use":
            self._use(node, target, ctm, viewport)
        elif tag == "svg" and node.parent is None:
            self.draw_children(node, target, ctm, viewport)
        elif tag == "svg":
            self._viewport(node, node, target, ctm, viewport)
        elif tag in ("g", "a", "switch"):
            self.draw_children(node, target, ctm, viewport)

    def _viewport(self, node: Node, content: Node, target, ctm, viewport, size=(None, None)) -> None:
        m, inner, rect = nested_viewport(node, viewport, size)
        if rect.is_empty:
            return
        overflow = node.specified.get("overflow", "hidden")
        if overflow not in CLIPPING_OVERFLOW:
            self.draw_children(content, target, ctm @ m, inner)
            return
        layer = np.zeros_like(target)
        self.draw_children(content, layer, ctm @ m, inner)
        layer *= self.rect_coverage(rect, ctm, target.shape[:2])[..., None]
        composite.over(target, layer)

    def _use(self, node: Node, target, ctm, viewport) -> None:
        ref = self.document.lookup(node.href)
        if ref is None or id(ref) in self._active_refs:
            return
        x, y = length(node, "x", viewport, "x"), length(node, "y", viewport, "y")
        instance = ref.clone(node)
        moved = ctm @ Matrix.translate(x, y)
        self._active_refs.add(id(ref))
        try:
            if ref.tag in ("symbol", "svg"):
                size = tuple(length(node, k, viewport, a) if node.get(k) is not None else None
                             for k, a in (("width", "x"), ("height", "y")))
                if ref.style.get("display") == "none" and ref.tag == "svg":
                    return
                shell = Node(ref.tag, {k: v for k, v in ref.attrs.items() if k not in ("x", "y")})
                shell.specified = ref.specified
                self._viewport(shell, instance, target, moved, viewport, size)
            else:
                self.draw(instance, target, moved, viewport)
        finally:
            self._active_refs.discard(id(ref))

    def rect_coverage(self, rect: BBox, ctm: Matrix, shape) -> np.ndarray:
        """Coverage of a user-space rectangle."""
        x, y, w, h = rect
        poly = ctm.apply_points(np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float64))
        return scanline.coverage([poly], shape[1], shape[0], "nonzero", self.samples)

    def user_tolerance(self, ctm: Matrix) -> float:
        """Flattening tolerance in user units for ``ctm``."""
        scale = ctm.mean_scale
        return self.tolerance / scale if scale > 0 else self.tolerance

    def fill_area(self, target, polygons, ctm: Matrix, rule: str, node: Node, prop: str, opacity: float,
                  bbox: BBox | None, viewport) -> None:
        """Rasterize user-space ``polygons`` and paint them with ``node``'s ``prop`` paint."""
        device = [ctm.apply_points(p) for p in polygons if len(p) >= 2]
        if not device:
            return
        pts = np.concatenate(device)
        h, w = target.shape[:2]
        x0 = max(0, int(math.floor(pts[:, 0].min())))
        y0 = max(0, int(math.floor(pts[:, 1].min())))
        x1 = min(w, int(math.ceil(pts[:, 0].max())))
        y1 = min(h, int(math.ceil(pts[:, 1].max())))
        if x1 <= x0 or y1 <= y0:
            return
        shifted = [p - (x0, y0) for p in device]
        cov = scanline.coverage(shifted, x1 - x0, y1 - y0, rule, self.samples)
        region_ctm = Matrix.translate(-x0, -y0) @ ctm
        paint = self.servers.paint(node, prop, opacity, bbox, region_ctm, (y1 - y0, x1 - x0), viewport)
        if paint is None:
            return
        sub = np.ascontiguousarray(target[y0:y1, x0:x1])
        composite.paint_coverage(sub, cov, paint)
        target[y0:y1, x0:x1] = sub

    def stroke_outline(self, node: Node, polylines, ctm: Matrix, viewport) -> list[np.ndarray]:
        """Stroke outline polygons (user space) for flattened polylines."""
        style = node.style
        units = node.units(viewport)
        width = parse_length(style.get("stroke-width"), units, "xy", 1.0)
        if width <= 0:
            return []
        dashes = parse_length_list(style.get("stroke-dasharray"), units)
        offset = parse_length(style.get("stroke-dashoffset"), units, "xy")
        try:
            miter = max(1.0, float(style.get("stroke-miterlimit", "4")))
        except ValueError:
            miter = 4.0
        join = style.get("stroke-linejoin", "miter")
        cap = style.get("stroke-linecap", "butt")
        join = join if join in ("miter", "round", "bevel") else "miter"
        cap = cap if cap in ("butt", "round", "square") else "butt"
        return stroke_polylines([(p.points, p.closed) for p in polylines], width, join, cap, miter,
                                dashes, offset, self.user_tolerance(ctm))

    def draw_shape(self, node: Node, target, ctm: Matrix, viewport) -> None:
        """Fill, stroke and mark a basic shape or path."""
        path = shape_path(node, viewport)
        if not path.segments:
            return
        polylines = flatten_path(path, self.user_tolerance(ctm))
        bounds = polylines_bbox(polylines)
        bbox = BBox.from_bounds(bounds) if bounds is not None else None
        style = node.style
        if style.get("visibility", "visible") == "visible" and polylines:
            fill_opacity = _unit(parse_fraction(style.get("fill-opacity"), 1.0))
            self.fill_area(target, [p.points for p in polylines], ctm, style.get("fill-rule", "nonzero"),
                           node, "fill", fill_opacity, bbox, viewport)
            if style.get("stroke", "none") != "none":
                outline = self.stroke_outline(node, polylines, ctm, viewport)
                stroke_opacity = _unit(parse_fraction(style.get("stroke-opacity"), 1.0))
                self.fill_area(target, outline, ctm, "nonzero", node, "stroke", stroke_opacity, bbox, viewport)
        draw_markers(self, node, path, target, ctm, viewport)

    def text_outlines(self, node: Node, ctm: Matrix, viewport):
        """``(run node, outline polygons)`` pairs for a ``text`` element."""
        tol = self.user_tolerance(ctm)
        for run in layout(node, viewport):
            if not run.strokes:
                continue
            outline = stroke_polylines([(s, False) for s in run.strokes], run.stroke_width,
                                       TEXT_STROKE_JOIN, TEXT_STROKE_JOIN, tolerance=tol)
            yield run.node, outline

    def draw_text(self, node: Node, target, ctm: Matrix, viewport) -> None:
        """Paint text with the stroke font using each run's fill."""
        bbox = node_bbox(node, viewport, self.document)
        for run_node, outline in self.text_outlines(node, ctm, viewport):
            if run_node.style.get("visibility", "visible") != "visible":
                continue
            opacity = _unit(parse_fraction(run_node.style.get("fill-opacity"), 1.0))
            self.fill_area(target, outline, ctm, "nonzero", run_node, "fill", opacity, bbox, viewport)
