"""Resampling an image through an affine map: nearest or bilinear, clamped or repeating."""
from __future__ import annotations

import numpy as np

from .. import _backend

PIXEL_CENTER = 0.5


def _coords(shape, inv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = shape[:2]
    py, px = np.mgrid[0:h, 0:w].astype(np.float64)
    px += PIXEL_CENTER
    py += PIXEL_CENTER
    return inv[0, 0] * px + inv[0, 1] * py + inv[0, 2], inv[1, 0] * px + inv[1, 1] * py + inv[1, 2]


def _index(i: np.ndarray, n: int, repeat: bool) -> np.ndarray:
    return np.mod(i, n) if repeat else np.clip(i, 0, n - 1)


def py_sample_image(out: np.ndarray, img: np.ndarray, inv: np.ndarray, bilinear: bool = True,
                    repeat: bool = False) -> None:
    """Fill ``out`` by sampling ``img`` at ``inv`` applied to each output pixel centre (numpy fallback)."""
    ih, iw = img.shape[:2]
    u, v = _coords(out.shape, np.asarray(inv, dtype=np.float64))
    if not bilinear:
        rows = _index(np.floor(v).astype(np.int64), ih, repeat)
        out[...] = img[rows, _index(np.floor(u).astype(np.int64), iw, repeat)]
        return
    u, v = u - PIXEL_CENTER, v - PIXEL_CENTER
    x0, y0 = np.floor(u), np.floor(v)
    fx, fy = (u - x0)[..., None], (v - y0)[..., None]
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    xa, xb = _index(x0, iw, repeat), _index(x0 + 1, iw, repeat)
    ya, yb = _index(y0, ih, repeat), _index(y0 + 1, ih, repeat)
    src = img.astype(np.float32, copy=False)
    top = src[ya, xa] * (1 - fx) + src[ya, xb] * fx
    bottom = src[yb, xa] * (1 - fx) + src[yb, xb] * fx
    out[...] = top * (1 - fy) + bottom * fy


def sample_image(out: np.ndarray, img: np.ndarray, inv: np.ndarray, *, bilinear: bool = True,
                 repeat: bool = False) -> None:
    """:func:`py_sample_image` through the Cython pattern module when it is built."""
    native = _backend.native("pattern")
    img = np.ascontiguousarray(img, dtype=np.float32)
    inv = np.ascontiguousarray(inv, dtype=np.float64)
    if native is not None and hasattr(native, "sample_image"):
        native.sample_image(out, img, inv, bilinear=bilinear, repeat=repeat)
    else:
        py_sample_image(out, img, inv, bilinear, repeat)
