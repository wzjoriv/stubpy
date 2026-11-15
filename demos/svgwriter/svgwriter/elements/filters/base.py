"""``<filter>`` and the shared filter-primitive base classes."""

from __future__ import annotations

import enum
from typing import Any, Union

from ..._internal._typing import Units
from .._mixins import CoreAttributes, ExternalResourcesAttribute, PresentationAttributes, XLinkAttributes
from .._viewport import Positioned
from ..base import Category, Child, Element
from ..container import Container

__all__ = [
    "Filter",
    "FilterInput",
    "FilterPrimitive",
    "SingleInput",
    "StandardInput",
    "TwoInputs",
    "resolve_input",
]


class StandardInput(str, enum.Enum):
    """Keywords accepted by ``in`` and ``in2``."""

    SOURCE_GRAPHIC = "SourceGraphic"
    SOURCE_ALPHA = "SourceAlpha"
    BACKGROUND_IMAGE = "BackgroundImage"
    BACKGROUND_ALPHA = "BackgroundAlpha"
    FILL_PAINT = "FillPaint"
    STROKE_PAINT = "StrokePaint"


FilterInput = Union[StandardInput, str, "FilterPrimitive"]


def resolve_input(value: FilterInput | None) -> StandardInput | str | None:
    """Turn a primitive into its ``result`` name; pass keywords through."""
    if isinstance(value, FilterPrimitive):
        return value.result
    return value


class FilterPrimitive(Positioned, PresentationAttributes, CoreAttributes, category=Category.FILTER_PRIMITIVE):
    """Base of every ``fe*`` element: sub-region and ``result`` name."""

    def __init__(self, *args: Child, result: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.update(result=result)

    @property
    def result(self) -> str:
        """The result name, generated on first access if unset."""
        name = self.attributes.get("result")
        if name is None:
            name = self.ensure_id() + "-out"
            self.attributes["result"] = name
        return str(name)

    def _input(self, name: str, value: FilterInput | None) -> None:
        self.update({name: resolve_input(value)})


class SingleInput(FilterPrimitive):
    """Primitives that read one input (``in``)."""

    def __init__(self, *args: Child, in_: FilterInput | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._input("in", in_)


class TwoInputs(SingleInput):
    """Primitives that combine ``in`` and ``in2``."""

    def __init__(self, *args: Child, in2: FilterInput | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._input("in2", in2)


class Filter(
    XLinkAttributes,
    Positioned,
    PresentationAttributes,
    ExternalResourcesAttribute,
    CoreAttributes,
    Container[Element],
    tag="filter",
    category=Category.CONTAINER,
):
    """``<filter>``: a graph of filter primitives.

    Parameters
    ----------
    *primitives : FilterPrimitive
        The primitives, in evaluation order.
    filter_units, primitive_units : {"userSpaceOnUse", "objectBoundingBox"}, optional
        Coordinate systems for the region and the primitives.
    filter_res : float or (float, float), optional
        Intermediate image resolution.
    **kwargs
        Region (``x``, ``y``, ``width``, ``height``), ``href`` and
        presentation/core attributes.
    """

    def __init__(
        self,
        *primitives: Child,
        filter_units: Units | None = None,
        primitive_units: Units | None = None,
        filter_res: float | tuple[float, float] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*primitives, **kwargs)
        self.update(filter_units=filter_units, primitive_units=primitive_units, filter_res=filter_res)

    @property
    def primitives(self) -> list[FilterPrimitive]:
        return [c for c in self if isinstance(c, FilterPrimitive)]
