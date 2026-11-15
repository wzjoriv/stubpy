"""Paint resolution: solid colors, gradients and patterns."""
from __future__ import annotations

import math
import re

import numpy as np

from ..dom.color import Color, parse_color
from ..dom.node import Node
from ..dom.transform import Matrix, parse_transform
from ..dom.units import parse_fraction, parse_length
from ..parse.viewport import parse_aspect_ratio, parse_viewbox, viewbox_transform
from ..raster import paint as paint_ops
from ._geometry import BBox

_URL_RE = re.compile(r"^\s*url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)\s*(.*)$")
GRADIENT_ATTRS = ("x1", "y1", "x2", "y2", "cx", "cy", "r", "fx", "fy",
                  "gradientUnits", "gradientTransform", "spreadMethod")
PATTERN_ATTRS = ("x", "y", "width", "height", "patternUnits", "patternContentUnits",
                 "patternTransform", "viewBox", "preserveAspectRatio")
OBB = "objectBoundingBox"
USER = "userSpaceOnUse"
MAX_TILE = 4096


def style_color(node: Node, prop: str, opacity_prop: str | None = None) -> Color | None:
    """A computed color property (``currentColor`` resolved) times its opacity property."""
    current = parse_color(node.style.get("color", "black")) or Color(0, 0, 0, 1)
    color = parse_color(node.style.get(prop, "black"), current)
    if color is None:
        return None
    if opacity_prop:
        color = color.with_alpha(min(1.0, max(0.0, parse_fraction(node.style.get(opacity_prop), 1.0))))
    return color


class PaintServers:
    """Builds the paint for a ``fill``/``stroke`` value."""

    def __init__(self, drawer):
        self.drawer = drawer
        self.document = drawer.document

    def paint(self, node: Node, prop: str, opacity: float, bbox: BBox | None, ctm: Matrix,
              shape: tuple[int, int], viewport: tuple[float, float]):
        """``None``, a premultiplied color tuple, or an ``(h, w, 4)`` paint image."""
        value = node.style.get(prop, "none").strip()
        if value == "none":
            return None
        match = _URL_RE.match(value)
        if match:
            server = self._document_for(node, prop).lookup("#" + match.group(1))
            fallback = match.group(2).strip()
            if server is not None and server.tag in ("linearGradient", "radialGradient", "pattern"):
                result = self._server(server, opacity, bbox, ctm, shape, viewport)
                if result is not None or server.tag != "pattern" or not fallback:
                    return result
            if not fallback or fallback == "none":
                return None
            value = fallback
        current = parse_color(node.style.get("color", "black")) or Color(0, 0, 0, 1)
        color = parse_color(value, current)
        if color is None:
            return None
        return color.with_alpha(opacity).premultiplied()

    def _document_for(self, node: Node, prop: str):
        """The document a property value came from (an inherited value may come from the referencing one)."""
        parent_doc = self.drawer.parent_document
        if parent_doc is None:
            return self.document
        origin = node
        while origin is not None and prop not in origin.specified:
            origin = origin.parent
        return parent_doc if origin is not None and parent_doc.contains(origin) else self.document

    def _server(self, server: Node, opacity, bbox, ctm, shape, viewport):
        if server.tag == "pattern":
            return self._pattern(server, opacity, bbox, ctm, shape, viewport)
        return self._gradient(server, opacity, bbox, ctm, shape, viewport)

    def _attrs(self, server: Node, names) -> dict[str, str]:
        found: dict[str, str] = {}
        for node in self.document.href_chain(server):
            for name in names:
                if name not in found and node.get(name) is not None:
                    found[name] = node.get(name)
        return found

    def _stops(self, server: Node) -> tuple[list[float], list[tuple]]:
        for node in self.document.href_chain(server):
            stops = [c for c in node.children if c.tag == "stop"]
            if stops:
                break
        else:
            return [], []
        offsets, colors, last = [], [], 0.0
        for stop in stops:
            off = min(1.0, max(0.0, parse_fraction(stop.get("offset"), 0.0)))
            last = max(last, off)
            offsets.append(last)
            colors.append(tuple(style_color(stop, "stop-color", "stop-opacity") or Color(0, 0, 0, 1)))
        return offsets, colors

    def _gradient(self, server: Node, opacity, bbox, ctm, shape, viewport):
        attrs = self._attrs(server, GRADIENT_ATTRS)
        offsets, colors = self._stops(server)
        if not offsets:
            return None
        colors = [(r, g, b, a * opacity) for r, g, b, a in colors]
        if len(offsets) == 1:
            return Color(*colors[0]).premultiplied()
        obb = attrs.get("gradientUnits", OBB) != USER
        if obb and (bbox is None or bbox.is_empty):
            return None
        m = ctm @ (bbox.matrix() if obb else Matrix()) @ parse_transform(attrs.get("gradientTransform"))
        if not m.is_invertible:
            return None
        inv = m.inverse().as_array()
        units = server.units(viewport)

        def coord(name: str, default: str, axis: str) -> float:
            raw = attrs.get(name, default)
            return parse_fraction(raw, 0.0) if obb else parse_length(raw, units, axis)

        linear_rgb = server.style.get("color-interpolation") == "linearRGB"
        table = paint_ops.build_lut(offsets, colors, linear_rgb=linear_rgb)
        spread = paint_ops.SPREAD.get(attrs.get("spreadMethod", "pad"), paint_ops.PAD)
        out = np.zeros(shape + (4,), dtype=np.float32)
        if server.tag == "linearGradient":
            paint_ops.linear_gradient(out, inv, coord("x1", "0%", "x"), coord("y1", "0%", "y"),
                                      coord("x2", "100%", "x"), coord("y2", "0%", "y"), table, spread)
        else:
            cx, cy = coord("cx", "50%", "x"), coord("cy", "50%", "y")
            r = coord("r", "50%", "xy")
            fx = coord("fx", attrs["fx"], "x") if "fx" in attrs else cx
            fy = coord("fy", attrs["fy"], "y") if "fy" in attrs else cy
            paint_ops.radial_gradient(out, inv, cx, cy, r, fx, fy, table, spread)
        return out

    def _pattern(self, server: Node, opacity, bbox, ctm, shape, viewport):
        attrs = self._attrs(server, PATTERN_ATTRS)
        content = next((n for n in self.document.href_chain(server) if n.children), server)
        obb = attrs.get("patternUnits", OBB) != USER
        if obb and (bbox is None or bbox.is_empty):
            return None
        units = server.units(viewport)

        if obb:
            fx, fy, fw, fh = (parse_fraction(attrs.get(k, "0"), 0.0) for k in ("x", "y", "width", "height"))
            x, y = bbox.x + fx * bbox.width, bbox.y + fy * bbox.height
            w, h = fw * bbox.width, fh * bbox.height
        else:
            x, y, w, h = (parse_length(attrs.get(k, "0"), units, axis)
                          for k, axis in (("x", "x"), ("y", "y"), ("width", "x"), ("height", "y")))
        if w <= 0 or h <= 0:
            return None
        pm = ctm @ parse_transform(attrs.get("patternTransform"))
        if not pm.is_invertible:
            return None
        sx, sy = pm.axis_scales
        tw = int(min(MAX_TILE, max(1, math.ceil(w * sx))))
        th = int(min(MAX_TILE, max(1, math.ceil(h * sy))))
        box = parse_viewbox(attrs.get("viewBox"))
        if box is not None:
            inner = viewbox_transform(box, w, h, parse_aspect_ratio(attrs.get("preserveAspectRatio")))
        elif attrs.get("patternContentUnits", USER) == OBB and bbox is not None:
            inner = Matrix.scale(bbox.width, bbox.height)
        else:
            inner = Matrix()
        tile_scale = Matrix.scale(tw / w, th / h)
        tile = np.zeros((th, tw, 4), dtype=np.float32)
        self.drawer.draw_children(content, tile, tile_scale @ inner, (w, h))
        if opacity < 1.0:
            tile *= np.float32(opacity)
        inv = (tile_scale @ Matrix.translate(-x, -y) @ pm.inverse()).as_array()
        out = np.zeros(shape + (4,), dtype=np.float32)
        paint_ops.pattern_fill(out, tile, inv)
        return out
