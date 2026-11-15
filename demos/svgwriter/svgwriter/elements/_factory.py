"""``ElementFactory``: ``doc.circle(...)``-style shortcuts.

Each shortcut builds one element from its arguments, adds it and returns
it. Shapes and text go to the insertion point; paint servers, clip paths,
masks, markers, filters and symbols go into ``<defs>`` with an id.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .base import Element
    from .clip import ClipPath, Marker, Mask
    from .filters.base import Filter
    from .paint import LinearGradient, Pattern, RadialGradient
    from .shapes import Circle, Ellipse, Line, Path, Polygon, Polyline, Rect
    from .structure import A, Group, Image, Switch, Symbol, Use
    from .text import Text

__all__ = ["ElementFactory"]

E = TypeVar("E", bound="Element")


class ElementFactory:
    """Shortcut methods shared by :class:`~svgwriter.Document` and containers.

    Every shortcut takes exactly the arguments of the element class it is
    named after.

    Examples
    --------
    >>> from svgwriter import Document
    >>> doc = Document(100, 100)
    >>> sky = doc.linear_gradient(x2=0, y2=1)
    >>> doc.rect(0, 0, 100, 100, fill=sky).get("fill") == sky.ref
    True
    >>> sky.parent is doc.defs
    True
    """

    __slots__ = ()

    @abstractmethod
    def _place(self, element: E) -> E:
        """Add *element* at the insertion point and return it."""

    @abstractmethod
    def _define(self, element: E) -> E:
        """Add *element* to the applicable ``<defs>`` and return it."""

    def rect(self, *args: Any, **kwargs: Any) -> Rect:
        """Add a :class:`~svgwriter.Rect`."""
        from .shapes import Rect

        return self._place(Rect(*args, **kwargs))

    def circle(self, *args: Any, **kwargs: Any) -> Circle:
        """Add a :class:`~svgwriter.Circle`."""
        from .shapes import Circle

        return self._place(Circle(*args, **kwargs))

    def ellipse(self, *args: Any, **kwargs: Any) -> Ellipse:
        """Add an :class:`~svgwriter.Ellipse`."""
        from .shapes import Ellipse

        return self._place(Ellipse(*args, **kwargs))

    def line(self, *args: Any, **kwargs: Any) -> Line:
        """Add a :class:`~svgwriter.Line`."""
        from .shapes import Line

        return self._place(Line(*args, **kwargs))

    def polyline(self, *args: Any, **kwargs: Any) -> Polyline:
        """Add a :class:`~svgwriter.Polyline`."""
        from .shapes import Polyline

        return self._place(Polyline(*args, **kwargs))

    def polygon(self, *args: Any, **kwargs: Any) -> Polygon:
        """Add a :class:`~svgwriter.Polygon`."""
        from .shapes import Polygon

        return self._place(Polygon(*args, **kwargs))

    def path(self, *args: Any, **kwargs: Any) -> Path:
        """Add a :class:`~svgwriter.Path`."""
        from .shapes import Path

        return self._place(Path(*args, **kwargs))

    def text(self, *args: Any, **kwargs: Any) -> Text:
        """Add a :class:`~svgwriter.Text`."""
        from .text import Text

        return self._place(Text(*args, **kwargs))

    def group(self, *args: Any, **kwargs: Any) -> Group:
        """Add a :class:`~svgwriter.Group`; use it in ``with`` to nest."""
        from .structure import Group

        return self._place(Group(*args, **kwargs))

    def link(self, *args: Any, **kwargs: Any) -> A:
        """Add an ``<a>`` (:class:`~svgwriter.A`)."""
        from .structure import A

        return self._place(A(*args, **kwargs))

    def switch(self, *args: Any, **kwargs: Any) -> Switch:
        """Add a :class:`~svgwriter.Switch`."""
        from .structure import Switch

        return self._place(Switch(*args, **kwargs))

    def use(self, *args: Any, **kwargs: Any) -> Use:
        """Add a :class:`~svgwriter.Use`."""
        from .structure import Use

        return self._place(Use(*args, **kwargs))

    def image(self, *args: Any, **kwargs: Any) -> Image:
        """Add an :class:`~svgwriter.Image`."""
        from .structure import Image

        return self._place(Image(*args, **kwargs))

    def linear_gradient(self, *args: Any, **kwargs: Any) -> LinearGradient:
        """Define a :class:`~svgwriter.LinearGradient` in ``<defs>``."""
        from .paint import LinearGradient

        return self._define(LinearGradient(*args, **kwargs))

    def radial_gradient(self, *args: Any, **kwargs: Any) -> RadialGradient:
        """Define a :class:`~svgwriter.RadialGradient` in ``<defs>``."""
        from .paint import RadialGradient

        return self._define(RadialGradient(*args, **kwargs))

    def pattern(self, *args: Any, **kwargs: Any) -> Pattern:
        """Define a :class:`~svgwriter.Pattern` in ``<defs>``."""
        from .paint import Pattern

        return self._define(Pattern(*args, **kwargs))

    def clip_path(self, *args: Any, **kwargs: Any) -> ClipPath:
        """Define a :class:`~svgwriter.ClipPath` in ``<defs>``."""
        from .clip import ClipPath

        return self._define(ClipPath(*args, **kwargs))

    def mask(self, *args: Any, **kwargs: Any) -> Mask:
        """Define a :class:`~svgwriter.Mask` in ``<defs>``."""
        from .clip import Mask

        return self._define(Mask(*args, **kwargs))

    def marker(self, *args: Any, **kwargs: Any) -> Marker:
        """Define a :class:`~svgwriter.Marker` in ``<defs>``."""
        from .clip import Marker

        return self._define(Marker(*args, **kwargs))

    def filter(self, *args: Any, **kwargs: Any) -> Filter:
        """Define a :class:`~svgwriter.Filter` in ``<defs>``."""
        from .filters.base import Filter

        return self._define(Filter(*args, **kwargs))

    def symbol(self, *args: Any, **kwargs: Any) -> Symbol:
        """Define a :class:`~svgwriter.Symbol` in ``<defs>``."""
        from .structure import Symbol

        return self._define(Symbol(*args, **kwargs))
