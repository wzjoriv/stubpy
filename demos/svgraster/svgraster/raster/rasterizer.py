"""An accumulating coverage canvas built on the C ``Rasterizer`` type."""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from .. import _backend
from .scanline import DEFAULT_SAMPLES, MAX_SAMPLES, NONZERO, prepare_polygons, py_fill_polygons, rule_code


class PyRasterizer:
    """Pure-Python stand-in for ``svgraster._scanline.Rasterizer``."""

    def __init__(self, width: int, height: int, samples: int = 4):
        if width < 0 or height < 0:
            raise ValueError("size must be non-negative")
        self._buffer = np.zeros((height, width), dtype=np.float32)
        self.samples = samples

    @property
    def width(self) -> int:
        """Columns in the coverage buffer."""
        return self._buffer.shape[1]

    @property
    def height(self) -> int:
        """Rows in the coverage buffer."""
        return self._buffer.shape[0]

    @property
    def samples(self) -> int:
        """Sub-scanlines per pixel row."""
        return self._samples

    @samples.setter
    def samples(self, value: int) -> None:
        if not 1 <= value <= MAX_SAMPLES:
            raise ValueError("samples out of range")
        self._samples = int(value)

    @classmethod
    def from_shape(cls, shape: tuple[int, int], samples: int = 4) -> PyRasterizer:
        """Build from a ``(height, width)`` shape."""
        return cls(shape[1], shape[0], samples)

    def fill(self, polygons, rule: int = NONZERO) -> None:
        """Accumulate coverage of ``polygons``."""
        py_fill_polygons(self._buffer, polygons, rule, self._samples)
        np.clip(self._buffer, 0.0, 1.0, out=self._buffer)

    def clear(self) -> None:
        """Reset coverage to zero."""
        self._buffer[...] = 0.0

    def coverage(self) -> memoryview:
        """A view of the coverage buffer."""
        return memoryview(self._buffer)

    def total(self) -> float:
        """Sum of all coverage (the covered area in pixels)."""
        return float(self._buffer.sum(dtype=np.float64))


_native = _backend.module("scanline")
_Base = _native.Rasterizer if _native is not None else PyRasterizer


class Rasterizer(_Base):
    """Coverage canvas with a default fill rule; extra options go to the base type."""

    def __init__(self, width: int, height: int, *, rule: str = "nonzero", **kwargs):
        super().__init__(width, height, **kwargs)
        self.rule = rule

    def fill(self, polygons: Iterable[np.ndarray], rule: str | int | None = None) -> None:
        """Accumulate polygons using ``rule`` or the default."""
        super().fill(prepare_polygons(polygons), rule_code(self.rule if rule is None else rule))

    def array(self) -> np.ndarray:
        """A copy of the coverage as a ``(height, width)`` float32 array."""
        return np.array(self.coverage(), dtype=np.float32, copy=True).reshape(self.height, self.width)


def make_rasterizer(width: int, height: int, samples: int = DEFAULT_SAMPLES, **kwargs) -> Rasterizer:
    """Forward ``**kwargs`` into :class:`Rasterizer`."""
    return Rasterizer(width, height, samples=samples, **kwargs)
