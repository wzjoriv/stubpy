"""Compositing and frame packing over the nanobind module."""
from __future__ import annotations

import numpy as np

from .. import _composite


def over(dst: np.ndarray, src: np.ndarray, opacity: float = 1.0) -> np.ndarray:
    """Composite ``src`` over ``dst`` in place and return ``dst``."""
    _composite.over(dst, src, opacity=opacity)
    return dst


def make_packer(width: int, height: int, **kwargs) -> _composite.FramePacker:
    """Forward ``**kwargs`` into :class:`FramePacker`."""
    return _composite.FramePacker(width, height, **kwargs)
