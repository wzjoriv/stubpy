"""Filter primitives over the pybind11 module."""
from __future__ import annotations

import numpy as np

from .. import _filters
from .._filters import BlendMode, LightSource, LightType, ResampleFilter, TransferFunction, TransferType


def gaussian_blur(img: np.ndarray, sx: float, sy: float | None = None) -> np.ndarray:
    """Blur with separate deviations; ``sy`` defaults to ``sx``."""
    return _filters.gaussian_blur(img, sx, sx if sy is None else sy)


def blur(img: np.ndarray, std: float, **kwargs) -> np.ndarray:
    """Blur with a single deviation; ``**kwargs`` go to :func:`gaussian_blur`."""
    return gaussian_blur(img, std, **kwargs)


__all__ = [
    "BlendMode",
    "LightSource",
    "LightType",
    "ResampleFilter",
    "TransferFunction",
    "TransferType",
    "blur",
    "gaussian_blur",
]
