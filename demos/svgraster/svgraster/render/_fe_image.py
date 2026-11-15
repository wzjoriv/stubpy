"""``feImage``: an external image or a referenced element rendered into the filter region."""
from __future__ import annotations

import numpy as np

from ..dom.transform import Matrix
from ..parse.viewport import ViewBox, parse_aspect_ratio, parse_viewbox, viewbox_transform
from ..raster.paint import convert_space
from ..raster.sample import sample_image
from ._filtering import LINEAR, FilterContext
from ._image import load_image


def fe_image(ctx: FilterContext, prim, space: str, rect):
    """Render the ``href`` target into a region-sized premultiplied image."""
    href = prim.href
    drawer = ctx.drawer
    if not href or drawer is None:
        return None
    out = np.zeros_like(ctx.source)
    if href.strip().startswith("#"):
        ref = drawer.document.lookup(href)
        if ref is None or ref is ctx.node:
            return None
        drawer.draw(ref.clone(ref.parent), out, ctx.ctm, ctx.viewport)
    else:
        image = load_image(drawer.document, href)
        if image is None:
            return None
        x, y, w, h = ctx.user_subregion(prim, rect)
        if w <= 0 or h <= 0:
            return None
        iw, ih = image.size
        box = parse_viewbox(image.document.root.get("viewBox")) if image.document is not None else None
        box = box or ViewBox(0.0, 0.0, iw, ih)
        m = ctx.ctm @ Matrix.translate(x, y) @ viewbox_transform(
            box, w, h, parse_aspect_ratio(prim.get("preserveAspectRatio")))
        if image.pixels is not None:
            if not m.is_invertible:
                return None
            sample = np.zeros_like(out)
            sample_image(sample, image.pixels, m.inverse().as_array())
            cover = drawer.rect_coverage(_clip_rect(x, y, w, h, m, box, ctx.ctm), ctx.ctm, out.shape[:2])
            out = sample * cover[..., None]
        else:
            from ._draw import Drawer

            sub = Drawer(image.document, samples=drawer.samples, tolerance=drawer.tolerance)
            sub._depth = drawer._depth + 1
            sub.draw_children(image.document.root, out, m, (box.width, box.height))
    if space == LINEAR:
        convert_space(out, True)
    return out


def _clip_rect(x, y, w, h, m: Matrix, box: ViewBox, ctm: Matrix):
    from ._geometry import BBox

    inner = ctm.inverse() @ m
    ix0, iy0, ix1, iy1 = inner.transform_rect(box.x, box.y, box.width, box.height)
    left, top = max(x, ix0), max(y, iy0)
    return BBox(left, top, min(x + w, ix1) - left, min(y + h, iy1) - top)
