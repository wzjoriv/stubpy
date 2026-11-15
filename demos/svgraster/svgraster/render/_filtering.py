"""Filter element evaluation: regions, resolution, inputs, color spaces and primitive chaining."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .. import filters as fx
from ..dom.node import Node
from ..dom.transform import Matrix
from ..dom.units import parse_fraction, parse_length, parse_numbers
from ..raster.paint import convert_space
from ._geometry import BBox

OBB = "objectBoundingBox"
USER = "userSpaceOnUse"
REGION_DEFAULTS = {"x": "-10%", "y": "-10%", "width": "120%", "height": "120%"}
SRGB, LINEAR = "srgb", "linear"
SOURCE_GRAPHIC = "SourceGraphic"
SOURCE_ALPHA = "SourceAlpha"
BACKGROUND_IMAGE = "BackgroundImage"
BACKGROUND_ALPHA = "BackgroundAlpha"
FILL_PAINT = "FillPaint"
STROKE_PAINT = "StrokePaint"
STANDARD_INPUTS = frozenset({SOURCE_GRAPHIC, SOURCE_ALPHA, BACKGROUND_IMAGE, BACKGROUND_ALPHA, FILL_PAINT,
                             STROKE_PAINT})
SNAP_EPS = 1e-6
MAX_FILTER_RES = 4096


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
    drawer: object = None
    node: Node | None = None
    origin: tuple[int, int] = (0, 0)
    canvas_shape: tuple[int, int] = (0, 0)
    res_scale: tuple[float, float] = (1.0, 1.0)
    region_px: tuple[int, int] = (0, 0)
    results: dict[str, Result] = field(default_factory=dict)
    last: Result | None = None
    _background: np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, int]:
        """``(height, width)`` of the filter region in pixels."""
        return self.source.shape[:2]

    @property
    def scale(self) -> float:
        """Mean user-to-pixel scale."""
        return self.ctm.mean_scale

    @property
    def full(self) -> tuple[int, int, int, int]:
        """The whole filter region as a pixel rectangle."""
        return (0, 0, self.shape[1], self.shape[0])

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

    def _fit(self, img: np.ndarray) -> np.ndarray:
        if img.shape[:2] == self.shape:
            return img
        return fx.resample(img, *self.shape)

    def background(self) -> np.ndarray:
        """``BackgroundImage`` cropped to the filter region."""
        if self._background is None:
            if self.drawer is None or self.node is None:
                self._background = np.zeros_like(self.source)
            else:
                canvas = self.drawer.background(self.node, self.canvas_shape)
                x0, y0 = self.origin
                h, w = self.region_px
                self._background = self._fit(np.ascontiguousarray(canvas[y0:y0 + h, x0:x0 + w]))
        return self._background

    def paint_input(self, prop: str) -> np.ndarray:
        """``FillPaint``/``StrokePaint``: the element's paint over the whole region."""
        out = np.zeros_like(self.source)
        if self.drawer is None or self.node is None:
            return out
        opacity = min(1.0, max(0.0, parse_fraction(self.node.style.get(f"{prop}-opacity"), 1.0)))
        paint = self.drawer.servers.paint(self.node, prop, opacity, self.bbox, self.ctm, self.shape, self.viewport)
        if paint is None:
            return out
        if isinstance(paint, np.ndarray):
            return np.ascontiguousarray(paint, dtype=np.float32)
        out[...] = np.asarray(paint, dtype=np.float32)
        return out

    def input(self, ref: str | None, space: str) -> Result:
        """Resolve an ``in``/``in2`` reference converted to ``space``."""
        full = self.full
        if ref in (SOURCE_ALPHA, BACKGROUND_ALPHA):
            base = self.source if ref == SOURCE_ALPHA else self.background()
            img = np.zeros_like(self.source)
            img[..., 3] = base[..., 3]
            return Result(img, space, full)
        if ref == BACKGROUND_IMAGE:
            found = Result(self.background(), SRGB, full)
        elif ref in (FILL_PAINT, STROKE_PAINT):
            found = Result(self.paint_input("fill" if ref == FILL_PAINT else "stroke"), SRGB, full)
        elif ref and ref in self.results:
            found = self.results[ref]
        elif ref == SOURCE_GRAPHIC or self.last is None:
            found = Result(self.source, SRGB, full)
        else:
            found = self.last
        img = found.image.copy()
        if found.space != space:
            convert_space(img, space == LINEAR)
        return Result(img, space, found.rect)

    def default_rect(self, prim: Node) -> tuple[int, int, int, int]:
        """Unspecified subregion attributes default to the filter region (Filter Effects 1)."""
        return self.full

    def user_subregion(self, prim: Node, default: tuple[int, int, int, int]) -> list[float]:
        """The primitive subregion ``[x, y, w, h]`` in user space."""
        inv = self.ctm.inverse()
        dx0, dy0, dx1, dy1 = inv.transform_rect(*default)
        values = [dx0, dy0, dx1 - dx0, dy1 - dy0]
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
        return values

    def subregion(self, prim: Node) -> tuple[int, int, int, int]:
        """The primitive subregion as a pixel rectangle ``(x, y, w, h)``."""
        default = self.default_rect(prim)
        if all(prim.get(k) is None for k in ("x", "y", "width", "height")):
            return default
        x0, y0, x1, y1 = self.ctm.transform_rect(*self.user_subregion(prim, default))
        h, w = self.shape
        px0, py0 = max(0, math.floor(x0 + SNAP_EPS)), max(0, math.floor(y0 + SNAP_EPS))
        px1, py1 = min(w, math.ceil(x1 - SNAP_EPS)), min(h, math.ceil(y1 - SNAP_EPS))
        return (px0, py0, max(0, px1 - px0), max(0, py1 - py0))


class FilterEngine:
    """Applies ``filter`` elements to rendered layers."""

    def __init__(self, drawer):
        self.drawer = drawer
        self.document = drawer.document

    def _attrs(self, filt: Node) -> dict[str, str]:
        found: dict[str, str] = {}
        for node in self.document.href_chain(filt):
            for k, v in node.attrs.items():
                found.setdefault(k, v)
        return found

    def region(self, attrs: dict[str, str], filt: Node, bbox: BBox | None, viewport) -> BBox | None:
        """The filter region in user space."""
        if attrs.get("filterUnits", OBB) != USER:
            if bbox is None or bbox.is_empty:
                return None
            fx_, fy, fw, fh = (parse_fraction(attrs.get(k, REGION_DEFAULTS[k])) for k in ("x", "y", "width", "height"))
            return BBox(bbox.x + fx_ * bbox.width, bbox.y + fy * bbox.height, fw * bbox.width, fh * bbox.height)
        units = filt.units(viewport)
        return BBox(*(parse_length(attrs.get(k, REGION_DEFAULTS[k]), units, axis)
                      for k, axis in (("x", "x"), ("y", "y"), ("width", "x"), ("height", "y"))))

    def apply(self, filt: Node, layer: np.ndarray, ctm: Matrix, bbox: BBox | None, viewport,
              node: Node | None = None) -> np.ndarray | None:
        """Filter ``layer``; ``None`` means the element is not rendered."""
        from ._primitives import HANDLERS

        attrs = self._attrs(filt)
        content = next((n for n in self.document.href_chain(filt) if any(c.tag.startswith("fe") for c in n.children)),
                       filt)
        region = self.region(attrs, filt, bbox, viewport)
        if region is None or region.is_empty:
            return None
        h, w = layer.shape[:2]
        rx0, ry0, rx1, ry1 = ctm.transform_rect(*region)
        x0, y0 = max(0, math.floor(rx0)), max(0, math.floor(ry0))
        x1, y1 = min(w, math.ceil(rx1)), min(h, math.ceil(ry1))
        out = np.zeros_like(layer)
        if x1 <= x0 or y1 <= y0:
            return out
        source = np.ascontiguousarray(layer[y0:y1, x0:x1])
        local = Matrix.translate(-x0, -y0) @ ctm
        res = parse_numbers(attrs.get("filterRes"))
        scale = (1.0, 1.0)
        if res and res[0] > 0:
            fw = min(MAX_FILTER_RES, max(1, int(res[0])))
            fh = min(MAX_FILTER_RES, max(1, int(res[1] if len(res) > 1 else res[0])))
            scale = (fw / (x1 - x0), fh / (y1 - y0))
            source = fx.resample(source, fh, fw)
            local = Matrix.scale(*scale) @ local
        elif res:
            return out
        ctx = FilterContext(source, local, bbox, region, viewport, attrs.get("primitiveUnits", USER) == OBB,
                            drawer=self.drawer, node=node, origin=(x0, y0), canvas_shape=(h, w), res_scale=scale,
                            region_px=(y1 - y0, x1 - x0))
        for prim in content.children:
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
        if final.shape[:2] != (y1 - y0, x1 - x0):
            final = fx.resample(final, y1 - y0, x1 - x0)
        out[y0:y1, x0:x1] = final
        return out
