"""Clipping, masking and markers."""

from __future__ import annotations

from typing import Any, Literal, Union

from .._internal._typing import Units
from ..attributes.length import LengthLike
from ._mixins import (
    ConditionalAttributes,
    CoreAttributes,
    ExternalResourcesAttribute,
    PresentationAttributes,
    Transformable,
)
from ._viewport import FitToViewBox, Positioned
from .base import Category, Child, Element
from .container import Container

__all__ = ["ClipPath", "Marker", "MarkerOrient", "Mask"]

MarkerOrient = Union[float, Literal["auto"]]


class ClipPath(
    Transformable,
    PresentationAttributes,
    ConditionalAttributes,
    ExternalResourcesAttribute,
    CoreAttributes,
    Container[Element],
    tag="clipPath",
    category=Category.CONTAINER,
):
    """``<clipPath>``: shapes whose union is the clipping region."""

    def __init__(self, *children: Child, clip_path_units: Units | None = None, **kwargs: Any) -> None:
        super().__init__(*children, **kwargs)
        self.update(clip_path_units=clip_path_units)


class Mask(
    Positioned,
    PresentationAttributes,
    ConditionalAttributes,
    ExternalResourcesAttribute,
    CoreAttributes,
    Container[Element],
    tag="mask",
    category=Category.CONTAINER,
):
    """``<mask>``: luminance of its content becomes the alpha mask."""

    def __init__(
        self,
        *children: Child,
        mask_units: Units | None = None,
        mask_content_units: Units | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*children, **kwargs)
        self.update(mask_units=mask_units, mask_content_units=mask_content_units)


class Marker(
    FitToViewBox,
    PresentationAttributes,
    ExternalResourcesAttribute,
    CoreAttributes,
    Container[Element],
    tag="marker",
    category=Category.CONTAINER,
):
    """``<marker>``: arrowheads and other symbols at path vertices.

    Parameters
    ----------
    *children : Element
        The marker graphics.
    ref_x, ref_y : float
        The point aligned with the vertex.
    marker_width, marker_height : length, optional
        Viewport size.
    marker_units : {"strokeWidth", "userSpaceOnUse"}, optional
        Coordinate system of the size.
    orient : float or "auto", optional
        Rotation; ``"auto"`` follows the path direction.
    """

    def __init__(
        self,
        *children: Child,
        ref_x: float = 0,
        ref_y: float = 0,
        marker_width: LengthLike | None = None,
        marker_height: LengthLike | None = None,
        marker_units: Literal["strokeWidth", "userSpaceOnUse"] | None = None,
        orient: MarkerOrient | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*children, **kwargs)
        self.update(
            ref_x=ref_x,
            ref_y=ref_y,
            marker_units=marker_units,
            marker_width=marker_width,
            marker_height=marker_height,
            orient=orient,
        )
