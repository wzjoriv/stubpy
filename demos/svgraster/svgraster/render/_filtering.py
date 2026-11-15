"""Filter element evaluation: regions, inputs, color spaces and primitive chaining."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..dom.node import Node
from ..dom.transform import Matrix
from ..dom.units import parse_fraction, parse_length
from ..raster.paint import convert_space
from ._geometry import BBox

OBB = "objectBoundingBox"
USER = "userSpaceOnUse"
REGION_DEFAULTS = {"x": "-10%", "y": "-10%", "width": "120%", "height": "120%"}
SRGB, LINEAR = "srgb", "linear"
SOURCE_GRAPHIC = "SourceGraphic"
SOURCE_ALPHA = "SourceAlpha"
SNAP_EPS = 1e-6
EMPTY_INPUTS = frozenset({"BackgroundImage", "BackgroundAlpha", "FillPaint", "StrokePaint"})


@dataclass
class Result:
    """A primitive result in a known color space and pixel subregion."""

    image: np.ndarray
    space: str
    rect: tuple[int, int, int, int]


@dataclass
class FilterContext:
    """State shared by the primitives of one filter application."""

    source: np.ndarray
    ctm: Matrix
    bbox: BBox | None
    region: BBox
    viewport: tuple[float, float]
    primitive_obb: bool
    results: dict[str, Result] = field(default_factory=dict)
    last: Result | None = None

    @property
    def shape(self) -> tuple[int, int]:
        """``(height, width)`` of the filter region in pixels."""
        return self.source.shape[:2]

    @property
    def scale(self) -> float:
        """Mean user-to-pixel scale."""
        return self.ctm.mean_scale

    def user_length(self, value: float, axis: str) -> float:
        """A primitive-units length converted to user units."""
        if not self.primitive_obb or self.bbox is None:
            return value
        if axis == "x":
            return value * self.bbox.width
        if axis == "y":
            return value * self.bbox.height
        return value * math.sqrt((self.bbox.width ** 2 + self.bbox.height ** 2) / 2.0)

    def px(self, value: float, axis: str) -> float:
        """A primitive-units length converted to pixels along ``axis``."""
        sx, sy = self.ctm.axis_scales
        factor = sx if axis == "x" else sy if axis == "y" else self.scale
        return self.user_length(value, axis) * factor

    def vector(self, dx: float, dy: float) -> tuple[float, float]:
        """A primitive-units offset converted to a pixel vector."""
        return self.ctm.apply_vector(self.user_length(dx, "x"), self.user_length(dy, "y"))

    def input(self, ref: str | None, space: str) -> Result:
        """Resolve an ``in``/``in2`` reference converted to ``space``."""
        full = (0, 0, self.shape[1], self.shape[0])
        if ref == SOURCE_ALPHA:
            img = np.zeros_like(self.source)
            img[..., 3] = self.source[..., 3]
            return Result(img, space, full)
        if ref in EMPTY_INPUTS:
            return Result(np.zeros_like(self.source), space, full)
        if ref and ref in self.results:
            found = self.results[ref]
        elif ref == SOURCE_GRAPHIC or self.last is None:
            found = Result(self.source, SRGB, full)
        else:
            found = self.last
        img = found.image.copy()
        if found.space != space:
            convert_space(img, space == LINEAR)
        return Result(img, space, found.rect)

    def subregion(self, prim: Node) -> tuple[int, int, int, int]:
        """The primitive subregion as a pixel rectangle ``(x, y, w, h)``."""
        region = self.region
        values = list(region)
        units = prim.units(self.viewport)
        for i, (name, axis) in enumerate((("x", "x"), ("y", "y"), ("width", "x"), ("height", "y"))):
            raw = prim.get(name)
            if raw is None:
                continue
            if self.primitive_obb and self.bbox is not None:
                frac = parse_fraction(raw)
                origin = (self.bbox.x, self.bbox.y, 0.0, 0.0)[i]
                values[i] = origin + frac * (self.bbox.width if axis == "x" else self.bbox.height)
            else:
                values[i] = parse_length(raw, units, axis)
        x0, y0, x1, y1 = self.ctm.transform_rect(*values)
        h, w = self.shape
        px0, py0 = max(0, math.floor(x0 + SNAP_EPS)), max(0, math.floor(y0 + SNAP_EPS))
        px1, py1 = min(w, math.ceil(x1 - SNAP_EPS)), min(h, math.ceil(y1 - SNAP_EPS))
        return (px0, py0, max(0, px1 - px0), max(0, py1 - py0))


class FilterEngine:
    """Applies ``filter`` elements to rendered layers."""

    def __init__(self, drawer):
        self.drawer = drawer
        self.document = drawer.document

    def region(self, filt: Node, bbox: BBox | None, viewport) -> BBox | None:
        """The filter region in user space."""
        if filt.get("filterUnits", OBB) != USER:
            if bbox is None or bbox.is_empty:
                return None
            fx, fy, fw, fh = (parse_fraction(filt.get(k, REGION_DEFAULTS[k])) for k in ("x", "y", "width", "height"))
            return BBox(bbox.x + fx * bbox.width, bbox.y + fy * bbox.height, fw * bbox.width, fh * bbox.height)
        units = filt.units(viewport)
        return BBox(*(parse_length(filt.get(k, REGION_DEFAULTS[k]), units, axis)
                      for k, axis in (("x", "x"), ("y", "y"), ("width", "x"), ("height", "y"))))

    def apply(self, filt: Node, layer: np.ndarray, ctm: Matrix, bbox: BBox | None, viewport) -> np.ndarray | None:
        """Filter ``layer``; ``None`` means the element is not rendered."""
        from ._primitives import HANDLERS

        region = self.region(filt, bbox, viewport)
        if region is None or region.is_empty:
            return None
        h, w = layer.shape[:2]
        rx0, ry0, rx1, ry1 = ctm.transform_rect(*region)
        x0, y0 = max(0, math.floor(rx0)), max(0, math.floor(ry0))
        x1, y1 = min(w, math.ceil(rx1)), min(h, math.ceil(ry1))
        out = np.zeros_like(layer)
        if x1 <= x0 or y1 <= y0:
            return out
        ctx = FilterContext(np.ascontiguousarray(layer[y0:y1, x0:x1]), Matrix.translate(-x0, -y0) @ ctm,
                            bbox, region, viewport, filt.get("primitiveUnits", USER) == OBB)
        for prim in filt.children:
            if not prim.tag.startswith("fe"):
                continue
            space = SRGB if prim.style.get("color-interpolation-filters") == "sRGB" else LINEAR
            rect = ctx.subregion(prim)
            handler = HANDLERS.get(prim.tag)
            image = handler(ctx, prim, space, rect) if handler is not None else None
            if image is None:
                image = np.zeros_like(ctx.source)
            image = np.ascontiguousarray(image, dtype=np.float32)
            rx, ry, rw, rh = rect
            clipped = np.zeros_like(image)
            clipped[ry:ry + rh, rx:rx + rw] = image[ry:ry + rh, rx:rx + rw]
            result = Result(clipped, space, rect)
            name = prim.get("result")
            if name:
                ctx.results[name] = result
            ctx.last = result
        if ctx.last is None:
            return out
        final = ctx.last.image
        if ctx.last.space != SRGB:
            convert_space(final, False)
        out[y0:y1, x0:x1] = final
        return out
