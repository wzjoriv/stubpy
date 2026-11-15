"""feMorphology, feConvolveMatrix and feDisplacementMap (numpy fallbacks)."""
from __future__ import annotations

import numpy as np

from ._blend import unpremultiply
from ._enums import Channel, EdgeMode, MorphologyOperator

HALF = 0.5


def _window_reduce(img: np.ndarray, radius: int, axis: int, reducer, fill: float) -> np.ndarray:
    if radius <= 0:
        return img
    n = img.shape[axis]
    pad = [(0, 0)] * img.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(img, pad, constant_values=fill)
    out = np.take(padded, np.arange(0, n), axis=axis)
    for i in range(1, 2 * radius + 1):
        out = reducer(out, np.take(padded, np.arange(i, i + n), axis=axis))
    return out


def py_morphology(img: np.ndarray, rx: int, ry: int, op: int = MorphologyOperator.ERODE) -> np.ndarray:
    """Erode (min) or dilate (max) over a ``(2ry+1) x (2rx+1)`` window clipped to the image."""
    if rx <= 0 and ry <= 0:
        return img.copy()
    erode = MorphologyOperator(op) == MorphologyOperator.ERODE
    reducer, fill = (np.minimum, np.inf) if erode else (np.maximum, -np.inf)
    out = _window_reduce(img.astype(np.float32), int(rx), 1, reducer, fill)
    return _window_reduce(out, int(ry), 0, reducer, fill).astype(np.float32)


def _edge_index(idx: np.ndarray, n: int, mode: EdgeMode) -> tuple[np.ndarray, np.ndarray]:
    if mode == EdgeMode.DUPLICATE:
        return np.clip(idx, 0, n - 1), np.ones(idx.shape, dtype=bool)
    if mode == EdgeMode.WRAP:
        return np.mod(idx, n), np.ones(idx.shape, dtype=bool)
    return np.clip(idx, 0, n - 1), (idx >= 0) & (idx < n)


def py_convolve_matrix(img: np.ndarray, kernel: np.ndarray, divisor: float = 1.0, bias: float = 0.0,
                       target_x: int = -1, target_y: int = -1, edge_mode: int = EdgeMode.DUPLICATE,
                       preserve_alpha: bool = False) -> np.ndarray:
    """Convolve with an ``(order_y, order_x)`` kernel per the SVG definition."""
    kernel = np.asarray(kernel, dtype=np.float64)
    oy, ox = kernel.shape
    tx = ox // 2 if target_x < 0 else target_x
    ty = oy // 2 if target_y < 0 else target_y
    divisor = divisor if divisor != 0 else 1.0
    mode = EdgeMode(edge_mode)
    h, w = img.shape[:2]
    if preserve_alpha:
        color, alpha = unpremultiply(img)
        src = np.concatenate([color, alpha], axis=-1)
    else:
        src = img.astype(np.float64)
    acc = np.zeros(src.shape, dtype=np.float64)
    for i in range(oy):
        rows, rvalid = _edge_index(np.arange(h) - ty + i, h, mode)
        for j in range(ox):
            cols, cvalid = _edge_index(np.arange(w) - tx + j, w, mode)
            weight = kernel[oy - i - 1, ox - j - 1]
            sample = src[rows][:, cols] * (rvalid[:, None] & cvalid[None, :])[..., None]
            acc += weight * sample
    out = np.clip(acc / divisor + bias, 0.0, 1.0)
    if preserve_alpha:
        out[..., 3] = src[..., 3]
        out[..., :3] *= out[..., 3:4]
    else:
        out[..., :3] = np.minimum(out[..., :3], out[..., 3:4])
    return out.astype(np.float32)


def py_displacement_map(img: np.ndarray, displacement: np.ndarray, scale: float,
                        x_channel: int = Channel.A, y_channel: int = Channel.A) -> np.ndarray:
    """Move pixels by ``scale * (channel - 0.5)``, sampling the nearest source pixel."""
    h, w = img.shape[:2]
    color, alpha = unpremultiply(displacement)
    straight = np.concatenate([color, alpha], axis=-1)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    sx = np.floor(xs + scale * (straight[..., int(x_channel)] - HALF) + HALF).astype(np.int64)
    sy = np.floor(ys + scale * (straight[..., int(y_channel)] - HALF) + HALF).astype(np.int64)
    valid = (sx >= 0) & (sx < w) & (sy >= 0) & (sy < h)
    out = img[np.clip(sy, 0, h - 1), np.clip(sx, 0, w - 1)].copy()
    out[~valid] = 0.0
    return out.astype(np.float32)
