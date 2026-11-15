"""Ready-made filters and markers, and the ``drawing`` decorator."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, Concatenate, Final

from .._internal._typing import Opacity, P
from ..color.color import Color
from ..document import Document
from ..elements.clip import Marker
from ..elements.filters import (
    CompositeOperator,
    FeComposite,
    FeFlood,
    FeGaussianBlur,
    FeMerge,
    FeOffset,
    Filter,
    StandardInput,
)
from ..elements.shapes import Path
from ..path.builder import PathBuilder

__all__ = ["arrow_marker", "drawing", "drop_shadow", "glow"]

DEFAULT_SHADOW_OFFSET: Final = 2.0
DEFAULT_BLUR: Final = 2.0
DEFAULT_SHADOW_OPACITY: Final = 0.5
FILTER_MARGIN: Final = "-20%"
FILTER_EXTENT: Final = "140%"
MARKER_SIZE: Final = 10.0


def drop_shadow(
    dx: float = DEFAULT_SHADOW_OFFSET,
    dy: float = DEFAULT_SHADOW_OFFSET,
    blur: float = DEFAULT_BLUR,
    color: Color | str = "black",
    opacity: Opacity = DEFAULT_SHADOW_OPACITY,
    **kwargs: Any,
) -> Filter:
    """A blurred, offset, tinted copy of the alpha merged under the source.

    Parameters
    ----------
    dx, dy : float
        Shadow offset.
    blur : float
        Gaussian standard deviation.
    color : Color or str
        Shadow color.
    opacity : float
        Shadow opacity.
    **kwargs
        Forwarded to :class:`~svgwriter.elements.filters.Filter`.
    """
    kwargs.setdefault("x", FILTER_MARGIN)
    kwargs.setdefault("y", FILTER_MARGIN)
    kwargs.setdefault("width", FILTER_EXTENT)
    kwargs.setdefault("height", FILTER_EXTENT)
    blurred = FeGaussianBlur(blur, in_=StandardInput.SOURCE_ALPHA)
    offset = FeOffset(dx, dy, in_=blurred)
    flood = FeFlood(color, opacity)
    tinted = FeComposite(CompositeOperator.IN, in_=flood, in2=offset)
    merge = FeMerge(tinted, StandardInput.SOURCE_GRAPHIC)
    return Filter(blurred, offset, flood, tinted, merge, **kwargs)


def glow(radius: float = DEFAULT_BLUR, **kwargs: Any) -> Filter:
    """A soft glow in the element's own colors."""
    blurred = FeGaussianBlur(radius, in_=StandardInput.SOURCE_GRAPHIC)
    return Filter(blurred, FeMerge(blurred, StandardInput.SOURCE_GRAPHIC), **kwargs)


def arrow_marker(color: Color | str = "black", size: float = MARKER_SIZE, **kwargs: Any) -> Marker:
    """A filled triangular arrowhead for ``marker-end``."""
    head = PathBuilder().move_to(0, 0).line_to(size, size / 2).line_to(0, size).close()
    kwargs.setdefault("orient", "auto")
    return Marker(
        Path(head, fill=color),
        ref_x=size,
        ref_y=size / 2,
        marker_width=size,
        marker_height=size,
        view_box=(0, 0, size, size),
        **kwargs,
    )


def drawing(width: float, height: float, **root: Any) -> Callable[[Callable[Concatenate[Document, P], object]], Callable[P, Document]]:
    """Turn ``f(doc, *args)`` into ``f(*args) -> Document``.

    Examples
    --------
    >>> @drawing(10, 10)
    ... def dot(doc, color="red"):
    ...     doc.add(Path("M5 5 h1", stroke=color))
    >>> isinstance(dot(), Document)
    True
    """

    def decorate(func: Callable[Concatenate[Document, P], object]) -> Callable[P, Document]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Document:
            doc = Document(width, height, **root)
            func(doc, *args, **kwargs)
            return doc

        return wrapper

    return decorate
