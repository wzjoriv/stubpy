"""Compositing of premultiplied float32 RGBA layers (nanobind or numpy)."""
from __future__ import annotations

import numpy as np

from .. import _backend

PORTER_DUFF = (
    "clear", "src", "dst", "src_over", "dst_over", "src_in", "dst_in",
    "src_out", "dst_out", "src_atop", "dst_atop", "xor", "plus",
)
MASK_MODES = {"luminance": 0, "alpha": 1}
LUMA_R, LUMA_G, LUMA_B = 0.2125, 0.7154, 0.0721
BYTE_MAX = 255.0
HALF = 0.5


def _factors(op: str, sa: np.ndarray, da: np.ndarray):
    one, zero = np.ones_like(sa), np.zeros_like(sa)
    table = {
        "clear": (zero, zero), "src": (one, zero), "dst": (zero, one),
        "src_over": (one, 1 - sa), "dst_over": (1 - da, one),
        "src_in": (da, zero), "dst_in": (zero, sa),
        "src_out": (1 - da, zero), "dst_out": (zero, 1 - sa),
        "src_atop": (da, 1 - sa), "dst_atop": (1 - da, sa),
        "xor": (1 - da, 1 - sa), "plus": (one, one),
    }
    if op not in table:
        raise ValueError(f"unknown Porter-Duff operator {op!r}")
    return table[op]


def py_porter_duff(dst: np.ndarray, src: np.ndarray, op: str = "src_over") -> np.ndarray:
    """``src op dst`` on premultiplied RGBA (numpy fallback)."""
    fa, fb = _factors(op, src[..., 3:4], dst[..., 3:4])
    return np.minimum(src * fa + dst * fb, 1.0).astype(np.float32)


def py_paint_coverage(dst: np.ndarray, coverage: np.ndarray, paint) -> None:
    """Composite a solid premultiplied color or a paint image through ``coverage``."""
    cov = coverage[..., None]
    if isinstance(paint, np.ndarray):
        src = paint * cov
    else:
        src = np.asarray(paint, dtype=np.float32) * cov
    dst *= 1.0 - src[..., 3:4]
    dst += src


def py_over(dst: np.ndarray, src: np.ndarray, opacity: float = 1.0) -> None:
    """``dst = src * opacity over dst`` in place."""
    s = src * np.float32(opacity)
    dst *= 1.0 - s[..., 3:4]
    dst += s


def py_mask_values(mask: np.ndarray, mode: int = 0) -> np.ndarray:
    """Per-pixel mask factors from a rendered mask layer."""
    if mode == MASK_MODES["alpha"]:
        return mask[..., 3].astype(np.float32)
    lum = LUMA_R * mask[..., 0] + LUMA_G * mask[..., 1] + LUMA_B * mask[..., 2]
    return np.clip(lum, 0.0, 1.0).astype(np.float32)


def py_to_uint8(img: np.ndarray, unpremultiply: bool = True) -> np.ndarray:
    """Premultiplied float32 to straight 8-bit RGBA."""
    out = img.astype(np.float32, copy=True)
    if unpremultiply:
        alpha = out[..., 3:4]
        safe = np.where(alpha > 0, alpha, 1.0)
        out[..., :3] = np.where(alpha > 0, out[..., :3] / safe, 0.0)
    return np.floor(np.clip(out, 0.0, 1.0) * BYTE_MAX + HALF).astype(np.uint8)


def py_to_float32(img: np.ndarray, premultiply: bool = True) -> np.ndarray:
    """Straight 8-bit RGBA to premultiplied float32."""
    out = img.astype(np.float32) / np.float32(BYTE_MAX)
    if premultiply:
        out[..., :3] *= out[..., 3:4]
    return out


def porter_duff(dst: np.ndarray, src: np.ndarray, op: str = "src_over") -> np.ndarray:
    """``src op dst`` as a new array."""
    native = _backend.native("composite")
    if native is not None:
        return native.porter_duff(dst, src, op)
    return py_porter_duff(dst, src, op)


def paint_coverage(dst: np.ndarray, coverage: np.ndarray, paint) -> None:
    """Composite ``paint`` (color tuple or image) through ``coverage`` into ``dst``."""
    native = _backend.native("composite")
    if native is None:
        py_paint_coverage(dst, coverage, paint)
    elif isinstance(paint, np.ndarray):
        native.paint_coverage(dst, coverage, np.ascontiguousarray(paint, dtype=np.float32))
    else:
        native.paint_coverage(dst, coverage, tuple(float(v) for v in paint))


def over(dst: np.ndarray, src: np.ndarray, opacity: float = 1.0) -> None:
    """Composite ``src`` over ``dst`` in place."""
    native = _backend.native("composite")
    if native is not None:
        native.over(dst, src, opacity=opacity)
    else:
        py_over(dst, src, opacity)


def mask_values(mask: np.ndarray, mode: str = "luminance") -> np.ndarray:
    """Mask factors from a rendered mask layer."""
    native = _backend.native("composite")
    code = MASK_MODES[mode]
    if native is not None:
        return native.mask_values(mask, code)
    return py_mask_values(mask, code)


def apply_mask(img: np.ndarray, factors: np.ndarray) -> None:
    """Multiply every channel of ``img`` by per-pixel ``factors`` in place."""
    native = _backend.native("composite")
    if native is not None:
        native.apply_mask(img, np.ascontiguousarray(factors, dtype=np.float32))
    else:
        img *= factors[..., None]


def to_uint8(img: np.ndarray, unpremultiply: bool = True) -> np.ndarray:
    """Premultiplied float32 to straight 8-bit RGBA."""
    native = _backend.native("composite")
    if native is not None:
        return native.to_uint8(np.ascontiguousarray(img, dtype=np.float32), unpremultiply=unpremultiply)
    return py_to_uint8(img, unpremultiply)


def to_float32(img: np.ndarray, premultiply: bool = True) -> np.ndarray:
    """Straight 8-bit RGBA to premultiplied float32."""
    native = _backend.native("composite")
    if native is not None:
        return native.to_float32(np.ascontiguousarray(img, dtype=np.uint8), premultiply=premultiply)
    return py_to_float32(img, premultiply)
