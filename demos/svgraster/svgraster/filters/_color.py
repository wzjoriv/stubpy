"""feColorMatrix and feComponentTransfer (numpy fallbacks)."""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from ._blend import unpremultiply
from ._enums import ColorMatrixType, TransferType

MATRIX_ROWS, MATRIX_COLS = 4, 5
LUM_COEFFS = (0.213, 0.715, 0.072)
L2A_COEFFS = (0.2125, 0.7154, 0.0721)
SAT_DIAG = (0.787, 0.285, 0.928)
HUE_COS = ((0.787, -0.715, -0.072), (-0.213, 0.285, -0.072), (-0.213, -0.715, 0.928))
HUE_SIN = ((-0.213, -0.715, 0.928), (0.143, 0.140, -0.283), (-0.787, 0.715, 0.072))


def color_matrix_values(kind: int, values: Sequence[float]) -> np.ndarray:
    """The 4x5 matrix for a feColorMatrix ``type`` and ``values``."""
    kind = ColorMatrixType(kind)
    m = np.zeros((MATRIX_ROWS, MATRIX_COLS), dtype=np.float64)
    m[:4, :4] = np.eye(4)
    if kind == ColorMatrixType.MATRIX:
        if len(values) == MATRIX_ROWS * MATRIX_COLS:
            m = np.asarray(values, dtype=np.float64).reshape(MATRIX_ROWS, MATRIX_COLS)
    elif kind == ColorMatrixType.SATURATE:
        s = values[0] if values else 1.0
        for i in range(3):
            for j in range(3):
                m[i, j] = LUM_COEFFS[j] + (SAT_DIAG[i] if i == j else -LUM_COEFFS[j]) * s
    elif kind == ColorMatrixType.HUE_ROTATE:
        rad = math.radians(values[0] if values else 0.0)
        cos, sin = math.cos(rad), math.sin(rad)
        for i in range(3):
            for j in range(3):
                m[i, j] = LUM_COEFFS[j] + cos * HUE_COS[i][j] + sin * HUE_SIN[i][j]
    else:
        m[:] = 0.0
        m[3, :3] = L2A_COEFFS
    return m


def py_color_matrix(img: np.ndarray, kind: int = ColorMatrixType.MATRIX,
                    values: Sequence[float] = ()) -> np.ndarray:
    """Apply a color matrix on unpremultiplied values."""
    m = color_matrix_values(kind, list(values))
    color, alpha = unpremultiply(img)
    rgba = np.concatenate([color, alpha], axis=-1)
    out = np.clip(rgba @ m[:, :4].T + m[:, 4], 0.0, 1.0)
    out[..., :3] *= out[..., 3:4]
    return out.astype(np.float32)


class PyTransferFunction:
    """Pure-Python stand-in for ``svgraster._filters.TransferFunction``.

    ``TransferFunction()`` is identity, ``(kind, table)`` is table/discrete,
    ``(slope, intercept)`` is linear, ``(amplitude, exponent, offset)`` is gamma.
    """

    def __init__(self, *args):
        self.kind = TransferType.IDENTITY
        self._values: list[float] = []
        self.slope, self.intercept = 1.0, 0.0
        self.amplitude, self.exponent, self.offset = 1.0, 1.0, 0.0
        if len(args) == 2 and not isinstance(args[1], (int, float)):
            self.kind = TransferType(args[0])
            self._values = [float(v) for v in args[1]]
        elif len(args) == 2:
            self.kind = TransferType.LINEAR
            self.slope, self.intercept = float(args[0]), float(args[1])
        elif len(args) == 3:
            self.kind = TransferType.GAMMA
            self.amplitude, self.exponent, self.offset = (float(a) for a in args)
        elif args:
            raise TypeError("unsupported TransferFunction arguments")

    @property
    def values(self) -> list[float]:
        """The table values."""
        return list(self._values)

    def __call__(self, c: np.ndarray) -> np.ndarray:
        """Apply to straight channel values in [0, 1]."""
        c = np.asarray(c, dtype=np.float64)
        v = np.asarray(self._values, dtype=np.float64)
        n = len(v)
        if self.kind == TransferType.TABLE and n:
            if n == 1:
                return np.full_like(c, v[0])
            k = np.clip(np.floor(c * (n - 1)).astype(np.int64), 0, n - 2)
            out = v[k] + (c * (n - 1) - k) * (v[k + 1] - v[k])
            return np.where(c >= 1.0, v[-1], out)
        if self.kind == TransferType.DISCRETE and n:
            return v[np.clip(np.floor(c * n).astype(np.int64), 0, n - 1)]
        if self.kind == TransferType.LINEAR:
            return self.slope * c + self.intercept
        if self.kind == TransferType.GAMMA:
            return self.amplitude * np.power(c, self.exponent) + self.offset
        return c


def py_component_transfer(img: np.ndarray, funcs: Sequence[PyTransferFunction]) -> np.ndarray:
    """Apply per-channel transfer functions on unpremultiplied values."""
    color, alpha = unpremultiply(img)
    rgba = np.concatenate([color, alpha], axis=-1)
    out = np.empty_like(rgba)
    for ch in range(4):
        out[..., ch] = funcs[ch](rgba[..., ch])
    out = np.clip(out, 0.0, 1.0)
    out[..., :3] *= out[..., 3:4]
    return out.astype(np.float32)
