"""A coverage canvas built on the C ``Rasterizer`` type."""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from .. import _scanline

RULES = {"nonzero": _scanline.NONZERO, "evenodd": _scanline.EVENODD}


class Rasterizer(_scanline.Rasterizer):
    """Coverage canvas with a default fill rule; extra options go to the C base type."""

    def __init__(self, width: int, height: int, *, rule: str = "nonzero", **kwargs):
        super().__init__(width, height, **kwargs)
        self.rule = rule

    def fill(self, polygons: Iterable[np.ndarray], rule: str | None = None) -> None:
        """Accumulate polygons using ``rule`` or the default."""
        super().fill([np.ascontiguousarray(p, dtype=np.float64) for p in polygons], RULES[rule or self.rule])

    def array(self) -> np.ndarray:
        """A copy of the coverage as a ``(height, width)`` float32 array."""
        return np.array(self.coverage(), dtype=np.float32, copy=True).reshape(self.height, self.width)


def make_rasterizer(width: int, height: int, samples: int = 4, **kwargs) -> Rasterizer:
    """Forward ``**kwargs`` into :class:`Rasterizer`."""
    return Rasterizer(width, height, samples=samples, **kwargs)
