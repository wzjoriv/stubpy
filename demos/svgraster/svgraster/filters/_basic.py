"""Blur, offset, flood, tile and merge (numpy fallbacks)."""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

KERNEL_SIGMAS = 3.0


def gaussian_kernel(sigma: float) -> np.ndarray:
    """A normalized 1-D Gaussian of radius ``ceil(3 * sigma)``."""
    radius = int(math.ceil(KERNEL_SIGMAS * sigma))
    xs = np.arange(-radius, radius + 1, dtype=np.float64)
    weights = np.exp(-(xs * xs) / (2.0 * sigma * sigma))
    return weights / weights.sum()


def _blur_axis(img: np.ndarray, sigma: float, axis: int) -> np.ndarray:
    if sigma <= 0:
        return img
    kernel = gaussian_kernel(sigma)
    radius = len(kernel) // 2
    n = img.shape[axis]
    pad = [(0, 0)] * img.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(img.astype(np.float64), pad)
    out = np.zeros(img.shape, dtype=np.float64)
    for i, w in enumerate(kernel):
        out += w * np.take(padded, np.arange(i, i + n), axis=axis)
    return out


def py_gaussian_blur(img: np.ndarray, sx: float, sy: float | None = None) -> np.ndarray:
    """Separable Gaussian blur with transparent edges."""
    sy = sx if sy is None else sy
    if sx <= 0 and sy <= 0:
        return img.copy()
    out = _blur_axis(_blur_axis(img, sx, 1), sy, 0)
    return np.asarray(out, dtype=np.float32)


def shift_whole(img: np.ndarray, ix: int, iy: int) -> np.ndarray:
    """Shift by whole pixels; vacated pixels become transparent."""
    h, w = img.shape[:2]
    out = np.zeros_like(img)
    if abs(ix) >= w or abs(iy) >= h:
        return out
    out[max(iy, 0):h + min(iy, 0), max(ix, 0):w + min(ix, 0)] = \
        img[max(-iy, 0):h - max(iy, 0), max(-ix, 0):w - max(ix, 0)]
    return out


def py_offset(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Shift by ``(dx, dy)`` pixels with bilinear interpolation for fractional offsets."""
    ix, iy = math.floor(dx), math.floor(dy)
    fx, fy = dx - ix, dy - iy
    src = img.astype(np.float64)
    out = np.zeros(img.shape, dtype=np.float64)
    taps = ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy))
    for ox, oy, weight in taps:
        if weight > 0:
            out += weight * shift_whole(src, ix + ox, iy + oy)
    return out.astype(np.float32)


def py_flood(height: int, width: int, color: Sequence[float]) -> np.ndarray:
    """A uniform premultiplied color."""
    out = np.empty((height, width, 4), dtype=np.float32)
    out[...] = np.asarray(color, dtype=np.float32)
    return out


def py_tile(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """Repeat the ``(x, y, w, h)`` pixel rectangle of ``img`` over its whole extent."""
    height, width = img.shape[:2]
    if w <= 0 or h <= 0:
        return np.zeros_like(img)
    cols = x + np.mod(np.arange(width) - x, w)
    rows = y + np.mod(np.arange(height) - y, h)
    valid_c = (cols >= 0) & (cols < width)
    valid_r = (rows >= 0) & (rows < height)
    out = img[np.clip(rows, 0, height - 1)][:, np.clip(cols, 0, width - 1)].copy()
    out[~valid_r] = 0.0
    out[:, ~valid_c] = 0.0
    return out


def py_merge(layers: Sequence[np.ndarray]) -> np.ndarray:
    """Composite ``layers`` bottom to top with source-over."""
    out = np.zeros_like(layers[0])
    for layer in layers:
        out = layer + out * (1.0 - layer[..., 3:4])
    return out.astype(np.float32)
