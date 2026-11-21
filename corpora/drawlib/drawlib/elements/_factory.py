"""``ElementFactory``: ``doc.circle(...)``-style shortcuts.

Each shortcut builds one element from its arguments, adds it and returns
it. Shapes go to the insertion point; paint servers and filters go into
``<defs>`` with an id.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from .base import Element
    from .effects import Filter, LinearGradient
    from .shapes import Circle, Line, Path, Rect
    from .structure import Group, Use

__all__ = ["ElementFactory"]

E = TypeVar("E", bound="Element")


class ElementFactory:
    """Shortcut methods shared by :class:`~drawlib.Document` and containers."""

    __slots__ = ()

    @abstractmethod
    def _place(self, element: E) -> E:
        """Add *element* at the insertion point and return it."""

    @abstractmethod
    def _define(self, element: E) -> E:
        """Add *element* to the applicable ``<defs>`` and return it."""

    def rect(self, *args: Any, **kwargs: Any) -> Rect:
        """Add a :class:`~drawlib.Rect`."""
        from .shapes import Rect

        return self._place(Rect(*args, **kwargs))

    def circle(self, *args: Any, **kwargs: Any) -> Circle:
        """Add a :class:`~drawlib.Circle`."""
        from .shapes import Circle

        return self._place(Circle(*args, **kwargs))

    def line(self, *args: Any, **kwargs: Any) -> Line:
        """Add a :class:`~drawlib.Line`."""
        from .shapes import Line

        return self._place(Line(*args, **kwargs))

    def path(self, *args: Any, **kwargs: Any) -> Path:
        """Add a :class:`~drawlib.Path`."""
        from .shapes import Path

        return self._place(Path(*args, **kwargs))

    def group(self, *args: Any, **kwargs: Any) -> Group:
        """Add a :class:`~drawlib.Group`; use it in ``with`` to nest."""
        from .structure import Group

        return self._place(Group(*args, **kwargs))

    def use(self, *args: Any, **kwargs: Any) -> Use:
        """Add a :class:`~drawlib.Use`."""
        from .structure import Use

        return self._place(Use(*args, **kwargs))

    def linear_gradient(self, *args: Any, **kwargs: Any) -> LinearGradient:
        """Define a :class:`~drawlib.LinearGradient` in ``<defs>``."""
        from .effects import LinearGradient

        return self._define(LinearGradient(*args, **kwargs))

    def filter(self, *args: Any, **kwargs: Any) -> Filter:
        """Define a :class:`~drawlib.Filter` in ``<defs>``."""
        from .effects import Filter

        return self._define(Filter(*args, **kwargs))
