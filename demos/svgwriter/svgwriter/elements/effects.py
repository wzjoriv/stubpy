"""Gradients, filters and animation elements."""

from __future__ import annotations

from typing import Any

from .._internal._typing import Self
from ..attributes.descriptors import Attr
from ..attributes.length import Length, LengthLike
from ._mixins import CoreAttributes, PresentationAttributes, XLinkAttributes
from .base import Category, Child, Element
from .container import GraphicsContainer

__all__ = ["Animate", "FeGaussianBlur", "Filter", "LinearGradient", "Set", "Stop"]


class Stop(CoreAttributes, PresentationAttributes, tag="stop", category=Category.OTHER):
    """``<stop>``: one color of a gradient."""

    offset = Attr[float](convert=float)

    def __init__(self, offset: float = 0.0, color: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(offset=offset, stop_color=color)


class LinearGradient(CoreAttributes, XLinkAttributes, GraphicsContainer, tag="linearGradient", category=Category.PAINT_SERVER):
    """``<linearGradient>`` between ``(x1, y1)`` and ``(x2, y2)``."""

    def __init__(
        self,
        *stops: Child,
        x1: LengthLike | None = None,
        y1: LengthLike | None = None,
        x2: LengthLike | None = None,
        y2: LengthLike | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*stops, **kwargs)
        self.update(x1=x1, y1=y1, x2=x2, y2=y2)

    @classmethod
    def horizontal(cls, *colors: str, **kwargs: Any) -> Self:
        """A left-to-right gradient evenly spread over *colors*."""
        last = max(len(colors) - 1, 1)
        return cls(*(Stop(i / last, color) for i, color in enumerate(colors)), x2=1, y2=0, **kwargs)


class Filter(CoreAttributes, XLinkAttributes, GraphicsContainer, tag="filter", category=Category.OTHER):
    """``<filter>``: a chain of primitives."""


class FeGaussianBlur(CoreAttributes, PresentationAttributes, tag="feGaussianBlur", category=Category.FILTER_PRIMITIVE):
    """``<feGaussianBlur>`` with a standard deviation."""

    std_deviation = Attr[Length](convert=Length.parse)

    def __init__(self, std_deviation: LengthLike = 0, in_: str | Element | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(std_deviation=std_deviation, in_=in_)


class Animate(CoreAttributes, XLinkAttributes, tag="animate", category=Category.ANIMATION):
    """``<animate>``: animates one attribute over time."""

    def __init__(self, attribute_name: str, values: str | None = None, dur: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(attribute_name=attribute_name, values=values, dur=dur)


class Set(CoreAttributes, XLinkAttributes, tag="set", category=Category.ANIMATION):
    """``<set>``: assigns an attribute value at a point in time."""

    def __init__(self, attribute_name: str, to: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(attribute_name=attribute_name, to=to)
