"""``Document``: a root ``<svg>`` plus a cursor for nested building."""

from __future__ import annotations

import enum
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

from ._internal._typing import AnyPath, Stack
from .elements.base import Element
from .elements.shapes import Circle, Ellipse, Line, Path, Polygon, Polyline, Rect, Shape
from .elements.structure import Defs, Desc, Group, Svg, Title

if TYPE_CHECKING:
    from .attributes.protocols import TextSink
    from .io.parser import Strictness

__all__ = ["Document", "ShapeKind"]

E = TypeVar("E", bound=Element)


class ShapeKind(str, enum.Enum):
    """Shape names accepted by :meth:`Document.add_shape`."""

    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> str:
        return name.lower()

    RECT = enum.auto()
    CIRCLE = enum.auto()
    ELLIPSE = enum.auto()
    LINE = enum.auto()
    POLYLINE = enum.auto()
    POLYGON = enum.auto()
    PATH = enum.auto()
    SQUARE = enum.auto()


class Document:
    """An SVG document under construction.

    Parameters
    ----------
    width, height : float, optional
        Canvas size; a matching ``viewBox`` is added unless one is given.
    root : Svg, optional
        Use an existing root instead of creating one.
    **kwargs
        Forwarded to :class:`~svgwriter.elements.Svg`.

    Examples
    --------
    >>> doc = Document(100, 100)
    >>> with doc.group(fill="red") as g:
    ...     _ = doc.add(Rect(10, 10, 20, 20))
    >>> len(g)
    1
    """

    def __init__(self, width: float | None = None, height: float | None = None, *, root: Svg | None = None, **kwargs: Any) -> None:
        if root is None:
            if width is not None and height is not None:
                root = Svg.with_size(width, height, **kwargs)
            else:
                root = Svg(width=width, height=height, **kwargs)
        self.root = root
        self._stack: Stack[Element] = Stack([root])

    @classmethod
    def from_string(cls, text: str | bytes, *, strictness: Strictness | None = None) -> Document:
        from .io.parser import Strictness, parse

        root = parse(text, strictness=strictness or Strictness.LENIENT)
        if not isinstance(root, Svg):
            raise ValueError(f"root element is <{root.tag}>, not <svg>")
        return cls(root=root)

    @classmethod
    def from_file(cls, path: AnyPath) -> Document:
        with open(path, "rb") as handle:
            return cls.from_string(handle.read())

    @classmethod
    @contextmanager
    def writing(cls, path: AnyPath, width: float, height: float, **kwargs: Any) -> Iterator[Document]:
        """Build a document and save it to *path* when the block exits."""
        options = kwargs.pop("options", None)
        doc = cls(width, height, **kwargs)
        yield doc
        doc.save(path, options=options)

    @property
    def current(self) -> Element:
        """Where :meth:`add` inserts: the innermost open group."""
        return self._stack.peek()

    @property
    def defs(self) -> Defs:
        return self.root.defs()

    def add(self, element: E) -> E:
        return self.current.append(element)

    def define(self, element: E) -> E:
        """Put *element* in ``<defs>`` (giving it an id) and return it."""
        element.ensure_id()
        return self.defs.append(element)

    def title(self, text: str) -> Title:
        return self.root.insert(0, Title(text))

    def describe(self, text: str) -> Desc:
        return self.add(Desc(text))

    @contextmanager
    def nest(self, element: E) -> Iterator[E]:
        """Add *element* and make it the insertion point inside the block."""
        self.add(element)
        self._stack.push(element)
        try:
            yield element
        finally:
            self._stack.pop()

    @contextmanager
    def group(self, *children: Element, **kwargs: Any) -> Iterator[Group]:
        """``with doc.group(**attrs) as g:`` nests subsequent adds in a ``<g>``."""
        with self.nest(Group(*children, **kwargs)) as group:
            yield group

    def add_shape(self, kind: ShapeKind | str, **kwargs: Any) -> Shape:
        """Create a shape by name, forwarding keywords to its class."""
        kind = ShapeKind(kind)
        if kind is ShapeKind.SQUARE:
            shape: Shape = self._square(**kwargs)
        elif kind in (ShapeKind.POLYLINE, ShapeKind.POLYGON):
            shape = self._poly(closed=kind is ShapeKind.POLYGON, **kwargs)
        else:
            shape = self._simple(kind, **kwargs)
        return self.add(shape)

    def _square(self, **kwargs: Any) -> Rect:
        size = kwargs.pop("size")
        return Rect.square(size, **kwargs)

    def _poly(self, *, closed: bool, **kwargs: Any) -> Polyline:
        points = kwargs.pop("points", ())
        return Polygon(points, **kwargs) if closed else Polyline(points, **kwargs)

    def _simple(self, kind: ShapeKind, **kwargs: Any) -> Shape:
        classes: dict[ShapeKind, type[Shape]] = {
            ShapeKind.RECT: Rect,
            ShapeKind.CIRCLE: Circle,
            ShapeKind.ELLIPSE: Ellipse,
            ShapeKind.LINE: Line,
            ShapeKind.PATH: Path,
        }
        return classes[kind](**kwargs)

    def __iter__(self) -> Iterator[Element]:
        return self.root.iter()

    def get_element_by_id(self, element_id: str) -> Element | None:
        return self.root.get_element_by_id(element_id)

    def to_string(self, **options: Any) -> str:
        return self.root.to_string(**options)

    def save(self, target: AnyPath | TextSink, **options: Any) -> None:
        self.root.save(target, **options)

    async def save_async(self, path: AnyPath, **options: Any) -> None:
        from .io._async import write_async

        await write_async(self.root, path, **options)
