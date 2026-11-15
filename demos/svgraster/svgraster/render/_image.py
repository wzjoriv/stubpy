"""The ``image`` element: raster images (PNG, JPEG) and SVG documents drawn into a viewport."""
from __future__ import annotations

import math
import warnings

import numpy as np

from ..dom.document import Document
from ..dom.node import Node
from ..dom.transform import Matrix
from ..io.images import decode_image, premultiplied
from ..io.resources import ResourceError, load
from ..parse.viewport import ViewBox, parse_aspect_ratio, parse_viewbox, viewbox_transform
from ..raster import composite
from ..raster.sample import sample_image
from ._geometry import BBox, length

SVG_TYPE = "image/svg+xml"
NEAREST_RENDERING = frozenset({"optimizeSpeed", "pixelated", "crisp-edges"})
MAX_NESTING = 8
CACHE_KEY = "images"


class LoadedImage:
    """A decoded raster (premultiplied float32) or a parsed SVG document."""

    def __init__(self, pixels: np.ndarray | None = None, document: Document | None = None):
        self.pixels = pixels
        self.document = document

    @property
    def size(self) -> tuple[float, float]:
        """Intrinsic ``(width, height)`` in CSS pixels."""
        if self.pixels is not None:
            return float(self.pixels.shape[1]), float(self.pixels.shape[0])
        from .renderer import intrinsic_size

        return intrinsic_size(self.document)


def load_image(document: Document, href: str) -> LoadedImage | None:
    """Load and cache the image an ``href`` points to; ``None`` (with a warning) on failure."""
    cache = document.cache.setdefault(CACHE_KEY, {})
    if href in cache:
        return cache[href]
    image = None
    try:
        res = load(href, document)
        if res.media_type == SVG_TYPE:
            base = res.path.parent if res.path is not None else document.base_dir
            image = LoadedImage(document=Document.parse(res.data, base_dir=base))
        else:
            image = LoadedImage(pixels=premultiplied(decode_image(res.data, res.media_type)))
    except (ResourceError, ValueError) as exc:
        shown = href if len(href) < 80 else href[:77] + "..."
        warnings.warn(f"svgraster: image {shown!r} not rendered: {exc}", stacklevel=3)
    cache[href] = image
    return image


def image_placement(node: Node, image: LoadedImage, viewport) -> tuple[BBox, Matrix, ViewBox]:
    """The viewport rectangle, the image-to-user transform and the image's own view box."""
    iw, ih = image.size
    x, y = length(node, "x", viewport, "x"), length(node, "y", viewport, "y")
    w = length(node, "width", viewport, "x", -1.0) if node.get("width") not in (None, "auto") else -1.0
    h = length(node, "height", viewport, "y", -1.0) if node.get("height") not in (None, "auto") else -1.0
    if w < 0 and h < 0:
        w, h = iw, ih
    elif w < 0:
        w = h * iw / ih if ih else 0.0
    elif h < 0:
        h = w * ih / iw if iw else 0.0
    if image.document is not None:
        box = parse_viewbox(image.document.root.get("viewBox"))
        if box is None:
            return BBox(x, y, w, h), Matrix.translate(x, y), ViewBox(0.0, 0.0, w, h)
    else:
        box = ViewBox(0.0, 0.0, iw, ih)
    m = Matrix.translate(x, y) @ viewbox_transform(box, w, h, parse_aspect_ratio(node.get("preserveAspectRatio")))
    return BBox(x, y, w, h), m, box


def _visible_rect(rect: BBox, m: Matrix, box: ViewBox) -> BBox:
    x0, y0, x1, y1 = m.transform_rect(box.x, box.y, box.width, box.height)
    left, top = max(rect.x, x0), max(rect.y, y0)
    right, bottom = min(rect.x + rect.width, x1), min(rect.y + rect.height, y1)
    return BBox(left, top, right - left, bottom - top)


def draw_image(drawer, node: Node, target: np.ndarray, ctm: Matrix, viewport) -> None:
    """Draw an ``image`` element onto ``target``."""
    href = node.href
    if not href or node.style.get("visibility", "visible") != "visible":
        return
    image = load_image(drawer.document, href)
    if image is None:
        return
    rect, m, box = image_placement(node, image, viewport)
    if rect.is_empty:
        return
    visible = _visible_rect(rect, m, box)
    if visible.is_empty:
        return
    layer = np.zeros_like(target)
    full = ctm @ m
    if image.pixels is not None:
        _draw_raster(drawer, node, image.pixels, layer, full, ctm, visible)
    else:
        _draw_svg(drawer, image.document, layer, full, box)
    layer *= drawer.rect_coverage(visible, ctm, target.shape[:2])[..., None]
    composite.over(target, layer)


def _draw_raster(drawer, node, pixels, layer, full: Matrix, ctm: Matrix, visible: BBox) -> None:
    if not full.is_invertible:
        return
    h, w = layer.shape[:2]
    x0, y0, x1, y1 = ctm.transform_rect(*visible)
    px0, py0 = max(0, math.floor(x0)), max(0, math.floor(y0))
    px1, py1 = min(w, math.ceil(x1)), min(h, math.ceil(y1))
    if px1 <= px0 or py1 <= py0:
        return
    region = np.zeros((py1 - py0, px1 - px0, 4), dtype=np.float32)
    inv = (full.inverse() @ Matrix.translate(px0, py0)).as_array()
    bilinear = node.style.get("image-rendering", "auto") not in NEAREST_RENDERING
    sample_image(region, pixels, inv, bilinear=bilinear)
    layer[py0:py1, px0:px1] = region


def _draw_svg(drawer, document: Document, layer, full: Matrix, box: ViewBox) -> None:
    from ._draw import Drawer

    if drawer._depth > MAX_NESTING:
        return
    sub = Drawer(document, samples=drawer.samples, tolerance=drawer.tolerance, renderer=drawer.renderer)
    sub._depth = drawer._depth + 1
    sub.draw_children(document.root, layer, full, (box.width, box.height))
