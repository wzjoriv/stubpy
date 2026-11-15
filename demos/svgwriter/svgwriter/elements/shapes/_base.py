"""The ``Shape`` base class and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ...attributes.length import Length
from ...path.data import BBox
from .._geometry import PathOperand
from .._mixins import GraphicsElement
from ..base import Category

__all__ = ["Shape", "parse_points", "user_units"]


def user_units(value: Any) -> float:
    """A length attribute in user units; unset counts as zero."""
    return 0.0 if value is None else Length.parse(value).to_user_units()


def parse_points(text: str) -> list[tuple[float, float]]:
    numbers = [float(n) for n in text.replace(",", " ").split()]
    if len(numbers) % 2:
        raise ValueError(f"points need an even number of coordinates, got {len(numbers)}")
    return list(zip(numbers[::2], numbers[1::2]))


class Shape(PathOperand, GraphicsElement, ABC, category=Category.SHAPE):
    """Base class for the basic shapes and paths.

    Every shape converts to a ``<path>`` (:meth:`to_path`) and supports the
    geometric operators of :class:`~svgwriter.elements.PathOperand`.
    """

    @property
    @abstractmethod
    def bbox(self) -> BBox:
        """Geometric bounding box in user units, ignoring stroke and transform."""
