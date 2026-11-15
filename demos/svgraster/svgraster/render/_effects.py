"""clipPath and mask evaluation."""
from __future__ import annotations

import numpy as np

from ..dom.node import Node
from ..dom.transform import Matrix
from ..dom.units import parse_fraction, parse_length
from ..parse.flatten import flatten_path
from ..raster import composite, scanline
from ._geometry import SHAPES, BBox, length, node_bbox, node_transform, shape_path

OBB = "objectBoundingBox"
USER = "userSpaceOnUse"
MASK_DEFAULTS = {"x": "-10%", "y": "-10%", "width": "120%", "height": "120%"}
MAX_CLIP_DEPTH = 16


class Effects:
    """Computes clip coverage and applies masks for a drawer."""

    def __init__(self, drawer):
        self.drawer = drawer
        self.document = drawer.document

    def clip_coverage(self, clip: Node, ctm: Matrix, bbox: BBox | None, shape, viewport,
                      depth: int = 0) -> np.ndarray:
        """Per-pixel coverage of a ``clipPath`` applied to an element with ``ctm`` and ``bbox``."""
        cov = np.zeros(shape, dtype=np.float32)
        if depth > MAX_CLIP_DEPTH:
            return cov
        m = ctm @ node_transform(clip)
        if clip.get("clipPathUnits", USER) == OBB:
            if bbox is None or bbox.is_empty:
                return cov
            m = m @ bbox.matrix()
        for child in clip.children:
            if child.style.get("display") == "none" or child.style.get("visibility", "visible") != "visible":
                continue
            child_cov = self._child_coverage(child, m, shape, viewport)
            if child_cov is None:
                continue
            ref = child.style.get("clip-path")
            nested = self.document.lookup(ref, "clipPath") if ref and ref != "none" else None
            if nested is not None:
                child_bbox = node_bbox(child, viewport, self.document)
                child_cov *= self.clip_coverage(nested, m @ node_transform(child), child_bbox, shape,
                                                viewport, depth + 1)
            np.maximum(cov, child_cov, out=cov)
        ref = clip.style.get("clip-path")
        own = self.document.lookup(ref, "clipPath") if ref and ref != "none" else None
        if own is not None and own is not clip:
            cov *= self.clip_coverage(own, ctm, bbox, shape, viewport, depth + 1)
        return cov

    def _child_coverage(self, child: Node, m: Matrix, shape, viewport) -> np.ndarray | None:
        local = m @ node_transform(child)
        rule = child.style.get("clip-rule", "nonzero")
        if child.tag == "use":
            ref = self.document.lookup(child.href)
            if ref is None or ref.tag not in SHAPES | {"text"}:
                return None
            moved = local @ Matrix.translate(length(child, "x", viewport, "x"), length(child, "y", viewport, "y"))
            return self._child_coverage(ref.clone(child), moved, shape, viewport)
        if child.tag == "text":
            polys = [p for _, outline in self.drawer.text_outlines(child, local, viewport) for p in outline]
            rule = "nonzero"
        elif child.tag in SHAPES:
            polys = [p.points for p in flatten_path(shape_path(child, viewport), self.drawer.user_tolerance(local))]
        else:
            return None
        device = [local.apply_points(p) for p in polys]
        return scanline.coverage(device, shape[1], shape[0], rule, self.drawer.samples)

    def apply_mask(self, mask: Node, layer: np.ndarray, ctm: Matrix, bbox: BBox | None, viewport) -> None:
        """Multiply ``layer`` by the luminance mask of ``mask``."""
        obb = mask.get("maskUnits", OBB) != USER
        if obb and (bbox is None or bbox.is_empty):
            layer[...] = 0.0
            return
        units = mask.units(viewport)
        if obb:
            fx, fy, fw, fh = (parse_fraction(mask.get(k, MASK_DEFAULTS[k])) for k in ("x", "y", "width", "height"))
            rect = BBox(bbox.x + fx * bbox.width, bbox.y + fy * bbox.height, fw * bbox.width, fh * bbox.height)
        else:
            rect = BBox(*(parse_length(mask.get(k, MASK_DEFAULTS[k]), units, axis)
                          for k, axis in (("x", "x"), ("y", "y"), ("width", "x"), ("height", "y"))))
        if rect.is_empty:
            layer[...] = 0.0
            return
        content = ctm
        if mask.get("maskContentUnits", USER) == OBB:
            if bbox is None or bbox.is_empty:
                layer[...] = 0.0
                return
            content = ctm @ bbox.matrix()
        mask_layer = np.zeros_like(layer)
        self.drawer.draw_children(mask, mask_layer, content, viewport)
        factors = composite.mask_values(mask_layer, "luminance")
        factors *= self.drawer.rect_coverage(rect, ctm, layer.shape[:2])
        composite.apply_mask(layer, factors)
