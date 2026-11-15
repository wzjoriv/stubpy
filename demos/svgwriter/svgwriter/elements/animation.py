"""SMIL animation elements."""

from __future__ import annotations

import enum
from collections.abc import Sequence
from typing import Any, Literal, Union

from .._internal._typing import Self
from ..path.builder import PathBuilder
from ..path.data import PathData
from ._mixins import ConditionalAttributes, CoreAttributes, ExternalResourcesAttribute, XLinkAttributes
from .base import Category, Child, ContentModel, Element

__all__ = [
    "Accumulate",
    "Additive",
    "Animate",
    "AnimateColor",
    "AnimateMotion",
    "AnimateTransform",
    "AnimationElement",
    "AnimationFill",
    "CalcMode",
    "Clock",
    "MPath",
    "Restart",
    "Set",
    "TransformType",
]

Clock = Union[str, float]
RepeatCount = Union[float, Literal["indefinite"]]


class Restart(str, enum.Enum):
    ALWAYS = "always"
    WHEN_NOT_ACTIVE = "whenNotActive"
    NEVER = "never"


class AnimationFill(str, enum.Enum):
    """The animation ``fill`` attribute (not paint)."""

    FREEZE = "freeze"
    REMOVE = "remove"


class CalcMode(str, enum.Enum):
    DISCRETE = "discrete"
    LINEAR = "linear"
    PACED = "paced"
    SPLINE = "spline"


class Additive(str, enum.Enum):
    REPLACE = "replace"
    SUM = "sum"


class Accumulate(str, enum.Enum):
    NONE = "none"
    SUM = "sum"


class TransformType(str, enum.Enum):
    TRANSLATE = "translate"
    SCALE = "scale"
    ROTATE = "rotate"
    SKEW_X = "skewX"
    SKEW_Y = "skewY"


def _clock(value: Clock | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return f"{value:g}s"


def _list(value: Any, separator: str = ";") -> Any:
    if isinstance(value, (list, tuple)):
        return separator.join(str(v) for v in value)
    return value


class AnimationElement(
    XLinkAttributes,
    ConditionalAttributes,
    ExternalResourcesAttribute,
    CoreAttributes,
    category=Category.ANIMATION,
):
    """Timing attributes shared by every animation element.

    Numeric clock values are written in seconds; ``float("inf")`` for
    ``repeat_count`` is written as ``indefinite``.
    """

    def __init__(
        self,
        *args: Child,
        begin: Clock | None = None,
        dur: Clock | None = None,
        end: Clock | None = None,
        min: Clock | None = None,
        max: Clock | None = None,
        restart: Restart = Restart.ALWAYS,
        repeat_count: RepeatCount | None = None,
        repeat_dur: Clock | None = None,
        fill: AnimationFill | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(
            begin=_clock(begin),
            dur=_clock(dur),
            end=_clock(end),
            min=_clock(min),
            max=_clock(max),
            restart=None if restart is Restart.ALWAYS else restart,
            repeat_count=repeat_count,
            repeat_dur=_clock(repeat_dur),
            fill=fill,
        )


class _AttributeTarget(Element):
    def __init__(
        self,
        *args: Child,
        attribute_name: str | None = None,
        attribute_type: Literal["CSS", "XML", "auto"] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(attribute_name=attribute_name, attribute_type=attribute_type)


class _ValueAnimation(Element):
    def __init__(
        self,
        *args: Child,
        values: Sequence[Any] | str | None = None,
        from_: Any = None,
        to: Any = None,
        by: Any = None,
        calc_mode: CalcMode | None = None,
        key_times: Sequence[float] | str | None = None,
        key_splines: Sequence[tuple[float, float, float, float]] | str | None = None,
        additive: Additive | None = None,
        accumulate: Accumulate | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if isinstance(key_splines, (list, tuple)):
            key_splines = ";".join(" ".join(f"{n:g}" for n in spline) for spline in key_splines)
        self.update(
            values=_list(values),
            from_=from_,
            to=to,
            by=by,
            calc_mode=calc_mode,
            key_times=_list(key_times),
            key_splines=key_splines,
            additive=additive,
            accumulate=accumulate,
        )


class Animate(AnimationElement, _ValueAnimation, _AttributeTarget, tag="animate"):
    """``<animate>``: interpolate one attribute over time.

    Examples
    --------
    >>> str(Animate.fade(1, 0, dur=2))
    '<animate attributeName="opacity" from="1" to="0" dur="2s"/>'
    """

    @classmethod
    def fade(cls, start: float, stop: float, **kwargs: Any) -> Self:
        return cls(attribute_name="opacity", from_=start, to=stop, **kwargs)


class Set(AnimationElement, _AttributeTarget, tag="set"):
    """``<set>``: assign a value for a duration."""

    def __init__(self, attribute_name: str | None = None, to: Any = None, **kwargs: Any) -> None:
        super().__init__(attribute_name=attribute_name, **kwargs)
        self.update(to=to)


class AnimateColor(AnimationElement, _ValueAnimation, _AttributeTarget, tag="animateColor"):
    """``<animateColor>``: color interpolation (deprecated in later SVG)."""


class AnimateTransform(AnimationElement, _ValueAnimation, _AttributeTarget, tag="animateTransform"):
    """``<animateTransform>``: animate the ``transform`` attribute."""

    def __init__(self, type: TransformType = TransformType.TRANSLATE, **kwargs: Any) -> None:
        kwargs.setdefault("attribute_name", "transform")
        super().__init__(**kwargs)
        self.update(type=type)

    @classmethod
    def spin(cls, cx: float = 0, cy: float = 0, **kwargs: Any) -> Self:
        """A full clockwise rotation about ``(cx, cy)``."""
        kwargs.setdefault("repeat_count", float("inf"))
        return cls(TransformType.ROTATE, from_=f"0 {cx:g} {cy:g}", to=f"360 {cx:g} {cy:g}", **kwargs)


class MPath(XLinkAttributes, ExternalResourcesAttribute, CoreAttributes, tag="mpath", category=Category.ANIMATION):
    """``<mpath>``: the motion path of ``animateMotion`` by reference."""

    def __init__(self, href: str | Element | None = None, **kwargs: Any) -> None:
        super().__init__(href=href, **kwargs)


class AnimateMotion(AnimationElement, _ValueAnimation, tag="animateMotion", content=ContentModel.ELEMENTS):
    """``<animateMotion>``: move an element along a path."""

    def __init__(
        self,
        *children: Child,
        path: PathData | PathBuilder | str | None = None,
        key_points: Sequence[float] | str | None = None,
        rotate: float | Literal["auto", "auto-reverse"] | None = None,
        origin: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*children, **kwargs)
        if isinstance(path, PathBuilder):
            path = path.build()
        elif isinstance(path, str):
            path = PathData(path)
        self.update(path=path, key_points=_list(key_points), rotate=rotate, origin=origin)
