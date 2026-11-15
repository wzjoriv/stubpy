"""Paint servers: gradients, stops and patterns."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Union

from .._internal._typing import Opacity, Self, SpreadMethod, Units
from ..attributes.length import LengthLike
from ..color.color import Color
from ..transform.transform import Transform, TransformLike, as_transform
from ._mixins import (
    ConditionalAttributes,
    CoreAttributes,
    ExternalResourcesAttribute,
    PresentationAttributes,
    Transformable,
    XLinkAttributes,
)
from ._viewport import FitToViewBox, Positioned
from .base import Category, Child, Element
from .container import Container

__all__ = ["Gradient", "LinearGradient", "Pattern", "RadialGradient", "Stop", "StopSpec"]

StopSpec = Union[tuple[float, Union[Color, str]], tuple[float, Union[Color, str], float]]


def _read_transform(element: Element, name: str) -> Transform:
    raw = element.attributes.get(name)
    return Transform() if raw is None else as_transform(raw)


def _write_transform(element: Element, name: str, value: TransformLike | None) -> None:
    if value is None:
        element.attributes.pop(name, None)
    else:
        element.attributes[name] = as_transform(value)


class Stop(PresentationAttributes, CoreAttributes, tag="stop", category=Category.GRADIENT):
    """``<stop>``: one color stop of a gradient."""

    def __init__(
        self,
        offset: float | str = 0,
        stop_color: Color | str | None = None,
        stop_opacity: Opacity | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(offset=offset, stop_color=stop_color, stop_opacity=stop_opacity)


class Gradient(
    Transformable,
    XLinkAttributes,
    ExternalResourcesAttribute,
    PresentationAttributes,
    CoreAttributes,
    Container[Stop],
    category=Category.GRADIENT,
):
    """Shared base of linear and radial gradients."""

    def __init__(
        self,
        *stops: Stop,
        gradient_units: Units | None = None,
        spread_method: SpreadMethod | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*stops, **kwargs)
        self.update(gradient_units=gradient_units, spread_method=spread_method)

    @property
    def transform(self) -> Transform:
        """Stored as ``gradientTransform``."""
        return _read_transform(self, "gradientTransform")

    @transform.setter
    def transform(self, value: TransformLike | None) -> None:
        _write_transform(self, "gradientTransform", value)

    def add_stop(self, offset: float, color: Color | str, opacity: Opacity | None = None, **kwargs: Any) -> Stop:
        return self.add(Stop(offset, color, opacity, **kwargs))

    @classmethod
    def from_colors(cls, colors: Sequence[Color | str], **kwargs: Any) -> Self:
        """Evenly spaced stops."""
        gradient = cls(**kwargs)
        last = max(len(colors) - 1, 1)
        for index, color in enumerate(colors):
            gradient.add_stop(index / last, color)
        return gradient

    @classmethod
    def from_stops(cls, stops: Iterable[StopSpec], **kwargs: Any) -> Self:
        gradient = cls(**kwargs)
        for spec in stops:
            gradient.add_stop(*spec)
        return gradient


class LinearGradient(Gradient, tag="linearGradient"):
    """``<linearGradient>``.

    Parameters
    ----------
    *stops : Stop
        Color stops.
    x1, y1, x2, y2 : length, optional
        The gradient vector.
    **kwargs
        ``gradient_units``, ``spread_method``, ``transform``, ``href`` and
        presentation/core attributes.
    """

    def __init__(
        self,
        *stops: Stop,
        x1: LengthLike | None = None,
        y1: LengthLike | None = None,
        x2: LengthLike | None = None,
        y2: LengthLike | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*stops, **kwargs)
        self.update(x1=x1, y1=y1, x2=x2, y2=y2)

    @classmethod
    def horizontal(cls, *colors: Color | str, **kwargs: Any) -> Self:
        return cls.from_colors(colors, x1=0, y1=0, x2=1, y2=0, **kwargs)

    @classmethod
    def vertical(cls, *colors: Color | str, **kwargs: Any) -> Self:
        return cls.from_colors(colors, x1=0, y1=0, x2=0, y2=1, **kwargs)


class RadialGradient(Gradient, tag="radialGradient"):
    """``<radialGradient>``."""

    def __init__(
        self,
        *stops: Stop,
        cx: LengthLike | None = None,
        cy: LengthLike | None = None,
        r: LengthLike | None = None,
        fx: LengthLike | None = None,
        fy: LengthLike | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*stops, **kwargs)
        self.update(cx=cx, cy=cy, r=r, fx=fx, fy=fy)


class Pattern(
    Transformable,
    Positioned,
    FitToViewBox,
    XLinkAttributes,
    ExternalResourcesAttribute,
    PresentationAttributes,
    ConditionalAttributes,
    CoreAttributes,
    Container[Element],
    tag="pattern",
    category=Category.PAINT_SERVER,
):
    """``<pattern>``: a tile of graphics used as paint."""

    def __init__(
        self,
        *children: Child,
        pattern_units: Units | None = None,
        pattern_content_units: Units | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*children, **kwargs)
        self.update(pattern_units=pattern_units, pattern_content_units=pattern_content_units)

    @property
    def transform(self) -> Transform:
        """Stored as ``patternTransform``."""
        return _read_transform(self, "patternTransform")

    @transform.setter
    def transform(self, value: TransformLike | None) -> None:
        _write_transform(self, "patternTransform", value)
