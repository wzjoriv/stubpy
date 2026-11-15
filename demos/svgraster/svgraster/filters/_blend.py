"""feBlend and feComposite (numpy fallbacks)."""
from __future__ import annotations

import numpy as np

from ._enums import BlendMode, CompositeOperator

LUM_R, LUM_G, LUM_B = 0.3, 0.59, 0.11
HALF = 0.5
QUARTER = 0.25


def unpremultiply(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Straight color (float64) and alpha."""
    alpha = img[..., 3:4].astype(np.float64)
    color = np.where(alpha > 0, img[..., :3] / np.where(alpha > 0, alpha, 1.0), 0.0)
    return color, alpha


def _lum(c: np.ndarray) -> np.ndarray:
    return (LUM_R * c[..., 0] + LUM_G * c[..., 1] + LUM_B * c[..., 2])[..., None]


def _clip_color(c: np.ndarray) -> np.ndarray:
    lum = _lum(c)
    lo = c.min(axis=-1, keepdims=True)
    hi = c.max(axis=-1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.where(lo < 0, lum + (c - lum) * lum / (lum - lo), c)
        c = np.where(hi > 1, lum + (c - lum) * (1 - lum) / (hi - lum), c)
    return c


def _set_lum(c: np.ndarray, lum: np.ndarray) -> np.ndarray:
    return _clip_color(c + (lum - _lum(c)))


def _sat(c: np.ndarray) -> np.ndarray:
    return c.max(axis=-1, keepdims=True) - c.min(axis=-1, keepdims=True)


def _set_sat(c: np.ndarray, sat: np.ndarray) -> np.ndarray:
    lo = c.min(axis=-1, keepdims=True)
    rng = _sat(c)
    return np.where(rng > 0, (c - lo) * sat / np.where(rng > 0, rng, 1.0), 0.0)


def _hard_light(cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    return np.where(cs <= HALF, cb * 2 * cs, cb + (2 * cs - 1) - cb * (2 * cs - 1))


def _soft_light(cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    d = np.where(cb <= QUARTER, ((16 * cb - 12) * cb + 4) * cb, np.sqrt(cb))
    return np.where(cs <= HALF, cb - (1 - 2 * cs) * cb * (1 - cb), cb + (2 * cs - 1) * (d - cb))


def blend_function(mode: int, cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    """The blend function ``B(cb, cs)`` on straight colors."""
    mode = BlendMode(mode)
    with np.errstate(divide="ignore", invalid="ignore"):
        table = {
            BlendMode.NORMAL: lambda: cs,
            BlendMode.MULTIPLY: lambda: cb * cs,
            BlendMode.SCREEN: lambda: cb + cs - cb * cs,
            BlendMode.DARKEN: lambda: np.minimum(cb, cs),
            BlendMode.LIGHTEN: lambda: np.maximum(cb, cs),
            BlendMode.OVERLAY: lambda: _hard_light(cs, cb),
            BlendMode.COLOR_DODGE: lambda: np.where(
                cb == 0, 0.0, np.where(cs >= 1, 1.0, np.minimum(1.0, cb / np.where(cs < 1, 1 - cs, 1.0)))),
            BlendMode.COLOR_BURN: lambda: np.where(
                cb >= 1, 1.0, np.where(cs <= 0, 0.0, 1 - np.minimum(1.0, (1 - cb) / np.where(cs > 0, cs, 1.0)))),
            BlendMode.HARD_LIGHT: lambda: _hard_light(cb, cs),
            BlendMode.SOFT_LIGHT: lambda: _soft_light(cb, cs),
            BlendMode.DIFFERENCE: lambda: np.abs(cb - cs),
            BlendMode.EXCLUSION: lambda: cb + cs - 2 * cb * cs,
            BlendMode.HUE: lambda: _set_lum(_set_sat(cs, _sat(cb)), _lum(cb)),
            BlendMode.SATURATION: lambda: _set_lum(_set_sat(cb, _sat(cs)), _lum(cb)),
            BlendMode.COLOR: lambda: _set_lum(cs, _lum(cb)),
            BlendMode.LUMINOSITY: lambda: _set_lum(cb, _lum(cs)),
        }
        return table[mode]()


def py_blend(src: np.ndarray, backdrop: np.ndarray, mode: int = BlendMode.NORMAL) -> np.ndarray:
    """Blend ``src`` (``in``) onto ``backdrop`` (``in2``)."""
    cs, a_s = unpremultiply(src)
    cb, a_b = unpremultiply(backdrop)
    mixed = blend_function(mode, cb, cs)
    color = (1 - a_b) * src[..., :3] + (1 - a_s) * backdrop[..., :3] + a_s * a_b * mixed
    alpha = a_s + a_b - a_s * a_b
    return np.clip(np.concatenate([color, alpha], axis=-1), 0.0, 1.0).astype(np.float32)


def py_composite(a: np.ndarray, b: np.ndarray, op: int = CompositeOperator.OVER,
                 k1: float = 0.0, k2: float = 0.0, k3: float = 0.0, k4: float = 0.0) -> np.ndarray:
    """``a op b`` on premultiplied images."""
    op = CompositeOperator(op)
    a64, b64 = a.astype(np.float64), b.astype(np.float64)
    aa, ab = a64[..., 3:4], b64[..., 3:4]
    if op == CompositeOperator.ARITHMETIC:
        out = np.clip(k1 * a64 * b64 + k2 * a64 + k3 * b64 + k4, 0.0, 1.0)
        out[..., :3] = np.minimum(out[..., :3], out[..., 3:4])
        return out.astype(np.float32)
    table = {
        CompositeOperator.OVER: lambda: a64 + b64 * (1 - aa),
        CompositeOperator.IN: lambda: a64 * ab,
        CompositeOperator.OUT: lambda: a64 * (1 - ab),
        CompositeOperator.ATOP: lambda: a64 * ab + b64 * (1 - aa),
        CompositeOperator.XOR: lambda: a64 * (1 - ab) + b64 * (1 - aa),
        CompositeOperator.LIGHTER: lambda: np.minimum(a64 + b64, 1.0),
    }
    return table[op]().astype(np.float32)
