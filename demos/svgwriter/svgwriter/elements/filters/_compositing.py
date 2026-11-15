"""Compositing primitives: blend, composite, merge, offset, flood, tile, image."""

from __future__ import annotations

import enum
from typing import Any

from ..._internal._typing import Opacity
from ...attributes.viewbox import PreserveAspectRatio
from ...color.color import Color
from .._mixins import CoreAttributes, ExternalResourcesAttribute, XLinkAttributes
from ..base import Child, ContentModel
from ..container import Container
from .base import FilterInput, FilterPrimitive, SingleInput, TwoInputs, resolve_input

__all__ = [
    "BlendMode",
    "CompositeOperator",
    "FeBlend",
    "FeComposite",
    "FeFlood",
    "FeImage",
    "FeMerge",
    "FeMergeNode",
    "FeOffset",
    "FeTile",
]


class BlendMode(str, enum.Enum):
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    DARKEN = "darken"
    LIGHTEN = "lighten"


class CompositeOperator(str, enum.Enum):
    OVER = "over"
    IN = "in"
    OUT = "out"
    ATOP = "atop"
    XOR = "xor"
    ARITHMETIC = "arithmetic"


class FeBlend(TwoInputs, tag="feBlend"):
    """``<feBlend>``: blend two inputs with a mode."""

    def __init__(self, mode: BlendMode = BlendMode.NORMAL, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(mode=None if mode is BlendMode.NORMAL else mode)


class FeComposite(TwoInputs, tag="feComposite"):
    """``<feComposite>``: Porter-Duff compositing or arithmetic."""

    def __init__(
        self,
        operator: CompositeOperator = CompositeOperator.OVER,
        *,
        k1: float | None = None,
        k2: float | None = None,
        k3: float | None = None,
        k4: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(operator=operator, k1=k1, k2=k2, k3=k3, k4=k4)


class FeOffset(SingleInput, tag="feOffset"):
    """``<feOffset>``: shift the input."""

    def __init__(self, dx: float = 0, dy: float = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(dx=dx, dy=dy)


class FeFlood(FilterPrimitive, tag="feFlood"):
    """``<feFlood>``: fill the sub-region with a color."""

    def __init__(self, flood_color: Color | str | None = None, flood_opacity: Opacity | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(flood_color=flood_color, flood_opacity=flood_opacity)


class FeTile(SingleInput, tag="feTile"):
    """``<feTile>``: repeat the input's sub-region."""


class FeImage(XLinkAttributes, ExternalResourcesAttribute, FilterPrimitive, tag="feImage"):
    """``<feImage>``: an external image or referenced element as input."""

    def __init__(
        self,
        href: str | None = None,
        *,
        preserve_aspect_ratio: PreserveAspectRatio | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(href=href, **kwargs)
        self.update(preserve_aspect_ratio=preserve_aspect_ratio)


class FeMergeNode(CoreAttributes, tag="feMergeNode", content=ContentModel.ELEMENTS):
    """``<feMergeNode>``: one layer of ``feMerge``."""

    def __init__(self, in_: FilterInput | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(in_=resolve_input(in_))


class FeMerge(FilterPrimitive, Container[FeMergeNode], tag="feMerge"):
    """``<feMerge>``: stack inputs with ``over``, first at the bottom."""

    def __init__(self, *nodes: Child | FilterInput, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        for node in nodes:
            self.add(node if isinstance(node, FeMergeNode) else FeMergeNode(node))  # type: ignore[arg-type]
