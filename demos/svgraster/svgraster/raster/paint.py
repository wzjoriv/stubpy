"""Gradient and pattern paint servers (Cython or numpy) and color-space conversion."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .. import _backend
from .sample import py_sample_image

PAD, REFLECT, REPEAT = 0, 1, 2
SPREAD = {"pad": PAD, "reflect": REFLECT, "repeat": REPEAT}
LUT_SIZE = 1024
FOCAL_LIMIT = 0.999
SRGB_KNEE = 0.04045
LINEAR_KNEE = 0.0031308
SRGB_SLOPE = 12.92
SRGB_GAMMA = 2.4
SRGB_A = 0.055
PIXEL_CENTER = 0.5


def srgb_to_linear_values(c: np.ndarray) -> np.ndarray:
    """The inverse sRGB transfer function on straight values."""
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= SRGB_KNEE, c / SRGB_SLOPE, ((np.maximum(c, 0.0) + SRGB_A) / (1 + SRGB_A)) ** SRGB_GAMMA)


def linear_to_srgb_values(c: np.ndarray) -> np.ndarray:
    """The sRGB transfer function on straight values."""
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, None)
    return np.where(c <= LINEAR_KNEE, c * SRGB_SLOPE, (1 + SRGB_A) * c ** (1 / SRGB_GAMMA) - SRGB_A)


def py_build_lut(offsets: Sequence[float], colors: Sequence[Sequence[float]], size: int = LUT_SIZE,
                 linear_rgb: bool = False) -> np.ndarray:
    """A ``(size, 4)`` premultiplied float32 color ramp from gradient stops."""
    off = np.asarray(offsets, dtype=np.float64)
    col = np.asarray(colors, dtype=np.float64).reshape(-1, 4).copy()
    if linear_rgb:
        col[:, :3] = srgb_to_linear_values(col[:, :3])
    t = np.arange(size, dtype=np.float64) / (size - 1)
    j = np.clip(np.searchsorted(off, t, side="right") - 1, 0, len(off) - 1)
    nxt = np.minimum(j + 1, len(off) - 1)
    span = off[nxt] - off[j]
    frac = np.where(span > 0, (t - off[j]) / np.where(span > 0, span, 1.0), 0.0)
    frac = np.clip(frac, 0.0, 1.0)[:, None]
    ramp = col[j] + (col[nxt] - col[j]) * frac
    ramp[t < off[0]] = col[0]
    ramp[t >= off[-1]] = col[-1]
    if linear_rgb:
        ramp[:, :3] = linear_to_srgb_values(ramp[:, :3])
    ramp[:, :3] *= ramp[:, 3:4]
    return ramp.astype(np.float32)


def _spread(t: np.ndarray, spread: int) -> np.ndarray:
    if spread == REPEAT:
        return t - np.floor(t)
    if spread == REFLECT:
        m = t - 2.0 * np.floor(t / 2.0)
        return np.where(m > 1.0, 2.0 - m, m)
    return np.clip(t, 0.0, 1.0)


def _user_coords(shape, inv: np.ndarray):
    h, w = shape[:2]
    py, px = np.mgrid[0:h, 0:w].astype(np.float64)
    px += PIXEL_CENTER
    py += PIXEL_CENTER
    return inv[0, 0] * px + inv[0, 1] * py + inv[0, 2], inv[1, 0] * px + inv[1, 1] * py + inv[1, 2]


def _lookup(out: np.ndarray, lut: np.ndarray, t: np.ndarray) -> None:
    idx = (t * (len(lut) - 1) + PIXEL_CENTER).astype(np.int64)
    out[...] = lut[np.clip(idx, 0, len(lut) - 1)]


def py_linear_gradient(out, inv, x1, y1, x2, y2, lut, spread=PAD) -> None:
    """Fill ``out`` with a linear gradient (numpy fallback)."""
    u, v = _user_coords(out.shape, inv)
    dx, dy = x2 - x1, y2 - y1
    den = dx * dx + dy * dy
    t = ((u - x1) * dx + (v - y1) * dy) / den if den > 0 else np.ones_like(u)
    _lookup(out, lut, _spread(t, spread))


def clamp_focal(cx, cy, r, fx, fy) -> tuple[float, float]:
    """Pull the focal point inside the end circle."""
    ex, ey = fx - cx, fy - cy
    dist = (ex * ex + ey * ey) ** 0.5
    limit = r * FOCAL_LIMIT
    if dist > limit and dist > 0:
        return cx + ex * limit / dist, cy + ey * limit / dist
    return fx, fy


def py_radial_gradient(out, inv, cx, cy, r, fx, fy, lut, spread=PAD) -> None:
    """Fill ``out`` with a focal radial gradient (numpy fallback)."""
    u, v = _user_coords(out.shape, inv)
    if r <= 0:
        _lookup(out, lut, np.ones_like(u))
        return
    fx, fy = clamp_focal(cx, cy, r, fx, fy)
    dx, dy = u - fx, v - fy
    ex, ey = fx - cx, fy - cy
    a = dx * dx + dy * dy
    b = ex * dx + ey * dy
    c = ex * ex + ey * ey - r * r
    safe_a = np.where(a > 0, a, 1.0)
    s = (-b + np.sqrt(np.maximum(b * b - a * c, 0.0))) / safe_a
    t = np.where(a > 0, 1.0 / np.where(s > 0, s, 1.0), 0.0)
    _lookup(out, lut, _spread(t, spread))


def py_pattern_fill(out, tile, inv, bilinear: bool = True) -> None:
    """Tile ``tile`` across ``out``; ``inv`` maps device to tile pixels (numpy fallback)."""
    py_sample_image(out, tile, inv, bilinear, repeat=True)


def py_convert_space(img: np.ndarray, to_linear: bool) -> None:
    """Convert a premultiplied image between sRGB and linearRGB in place."""
    alpha = img[..., 3:4].astype(np.float64)
    safe = np.where(alpha > 0, alpha, 1.0)
    straight = img[..., :3] / safe
    conv = srgb_to_linear_values(straight) if to_linear else linear_to_srgb_values(straight)
    img[..., :3] = np.where(alpha > 0, conv * alpha, 0.0)


class PyGradientLUT:
    """Pure-Python stand-in for ``svgraster._paint.GradientLUT``."""

    def __init__(self, offsets, colors, size: int = LUT_SIZE, linear_rgb: bool = False):
        if size < 2:
            raise ValueError("size must be at least 2")
        if len(offsets) == 0 or len(offsets) != len(colors):
            raise ValueError("offsets and colors must be non-empty and equally long")
        self._table = py_build_lut(offsets, colors, size, linear_rgb)
        self._linear_rgb = bool(linear_rgb)

    @property
    def size(self) -> int:
        """Entries in the ramp."""
        return len(self._table)

    @property
    def linear_rgb(self) -> bool:
        """Whether stops were interpolated in linearRGB."""
        return self._linear_rgb

    @property
    def table(self) -> np.ndarray:
        """The ``(size, 4)`` premultiplied ramp."""
        return self._table

    def sample(self, t: float, spread: int = PAD) -> tuple[float, float, float, float]:
        """The premultiplied color at parameter ``t``."""
        tt = float(_spread(np.array([t], dtype=np.float64), spread)[0])
        idx = min(max(int(tt * (self.size - 1) + PIXEL_CENTER), 0), self.size - 1)
        return tuple(float(v) for v in self._table[idx])


_native = _backend.module("paint")
_Base = _native.GradientLUT if _native is not None else PyGradientLUT


class GradientLUT(_Base):
    """A gradient color ramp; ``**kwargs`` (``size``, ``linear_rgb``) go to the base type."""

    def __init__(self, offsets, colors, **kwargs):
        offsets = np.ascontiguousarray(offsets, dtype=np.float64)
        colors = np.ascontiguousarray(colors, dtype=np.float64).reshape(-1, 4)
        super().__init__(offsets, colors, **kwargs)


def build_lut(offsets, colors, size: int = LUT_SIZE, linear_rgb: bool = False) -> np.ndarray:
    """The premultiplied ramp table, using Cython when built."""
    native = _backend.native("paint")
    if native is not None:
        lut = native.GradientLUT(np.ascontiguousarray(offsets, dtype=np.float64),
                                 np.ascontiguousarray(colors, dtype=np.float64).reshape(-1, 4),
                                 size=size, linear_rgb=linear_rgb)
        return np.asarray(lut.table)
    return py_build_lut(offsets, colors, size, linear_rgb)


def linear_gradient(out, inv, x1, y1, x2, y2, table, spread=PAD) -> None:
    """Fill ``out`` with a linear gradient using Cython when built."""
    native = _backend.native("paint")
    fn = native.linear_gradient if native is not None else py_linear_gradient
    fn(out, np.ascontiguousarray(inv, dtype=np.float64), x1, y1, x2, y2,
       np.ascontiguousarray(table, dtype=np.float32), spread)


def radial_gradient(out, inv, cx, cy, r, fx, fy, table, spread=PAD) -> None:
    """Fill ``out`` with a radial gradient using Cython when built."""
    native = _backend.native("paint")
    fn = native.radial_gradient if native is not None else py_radial_gradient
    fn(out, np.ascontiguousarray(inv, dtype=np.float64), cx, cy, r, fx, fy,
       np.ascontiguousarray(table, dtype=np.float32), spread)


def pattern_fill(out, tile, inv, bilinear: bool = True) -> None:
    """Tile an image across ``out`` (bilinear by default) using Cython when built."""
    native = _backend.native("pattern")
    tile = np.ascontiguousarray(tile, dtype=np.float32)
    inv = np.ascontiguousarray(inv, dtype=np.float64)
    (native.pattern_fill if native is not None else py_pattern_fill)(out, tile, inv, bilinear)


def convert_space(img: np.ndarray, to_linear: bool) -> None:
    """sRGB <-> linearRGB on a premultiplied image in place, using Cython when built."""
    native = _backend.native("pattern")
    if native is not None:
        (native.srgb_to_linear if to_linear else native.linear_to_srgb)(img)
    else:
        py_convert_space(img, to_linear)
