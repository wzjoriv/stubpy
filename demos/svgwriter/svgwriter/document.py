"""``Document``: a root ``<svg>`` plus a cursor for nested building."""

from __future__ import annotations

import enum
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

from ._internal._typing import AnyPath, Self, Stack
from .elements._factory import ElementFactory
from .elements.base import Element
from .elements.container import attach_cursor, flatten
from .elements.shapes import Circle, Line, Path, Rect, Shape
from .elements.structure import Defs, Svg

if TYPE_CHECKING:
    from .attributes.protocols import TextSink
    from .attributes.values import FuncIRI

__all__ = ["Document", "ShapeKind"]

E = TypeVar("E", bound=Element)


class ShapeKind(str, enum.Enum):
    """Shape names accepted by :meth:`Document.add_shape`."""

    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> str:
        return name.lower()

    RECT = enum.auto()
    CIRCLE = enum.auto()
    LINE = enum.auto()
    PATH = enum.auto()
    SQUARE = enum.auto()


class Document(ElementFactory):
    """An SVG document under construction.

    Shortcut methods (``doc.circle(...)``, ``doc.linear_gradient(...)``)
    build an element, add it and return it; definitions go into ``<defs>``.
    Containers returned by shortcuts nest when used with ``with``.

    >>> doc = Document(100, 100)
    >>> with doc.group(fill="red") as g:
    ...     _ = doc.rect(10, 10, 20, 20)
    ...     _ = doc.circle(50, 50, 10)
    >>> len(g)
    2
    """

    def __init__(self, width: float | None = None, height: float | None = None, *, root: Svg | None = None, **kwargs: Any) -> None:
        if root is None:
            if width is not None and height is not None:
                root = Svg.with_size(width, height, **kwargs)
            else:
                root = Svg(width=width, height=height, **kwargs)
        self.root = root
        self._stack: Stack[Element] = Stack([root])
        attach_cursor(root, self._stack)

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
        """Where :meth:`add` inserts: the innermost open container."""
        return self._stack.peek()

    @property
    def defs(self) -> Defs:
        return self.root.defs()

    def _place(self, element: E) -> E:
        attach_cursor(element, self._stack)
        return self.current.append(element)

    def _define(self, element: E) -> E:
        element.ensure_id()
        if element.parent is not self.defs:
            self.defs.append(element)
        attach_cursor(element, self._stack)
        return element

    def add(self, element: E) -> E:
        """Add *element* at the insertion point and return it."""
        return self._place(element)

    @contextmanager
    def nest(self, element: E) -> Iterator[E]:
        """Add *element* and make it the insertion point inside the block."""
        self.add(element)
        self._stack.push(element)
        try:
            yield element
        finally:
            self._stack.pop()

    def __iadd__(self, elements: Element | Iterable[Element]) -> Self:
        for element in flatten(elements):
            self._place(element)  # type: ignore[type-var]
        return self

    def __mod__(self, element: Element) -> FuncIRI:
        if not isinstance(element, Element):
            return NotImplemented
        return self._define(element).ref

    def __imod__(self, elements: Element | Iterable[Element]) -> Self:
        for element in flatten(elements):
            self._define(element)  # type: ignore[type-var]
        return self

    def add_shape(self, kind: ShapeKind | str, **kwargs: Any) -> Shape:
        """Create a shape by name, forwarding keywords to its class."""
        kind = ShapeKind(kind)
        if kind is ShapeKind.SQUARE:
            shape: Shape = Rect.square(kwargs.pop("size"), **kwargs)
        else:
            classes: dict[ShapeKind, type[Shape]] = {
                ShapeKind.RECT: Rect,
                ShapeKind.CIRCLE: Circle,
                ShapeKind.LINE: Line,
                ShapeKind.PATH: Path,
            }
            shape = classes[kind](**kwargs)
        return self.add(shape)

    def __iter__(self) -> Iterator[Element]:
        return self.root.iter()

    def to_string(self, **options: Any) -> str:
        return self.root.to_string(**options)

    def __str__(self) -> str:
        return self.root.to_string(xml_declaration=False)

    def save(self, target: AnyPath | TextSink, **options: Any) -> None:
        self.root.save(target, **options)

    async def save_async(self, path: AnyPath, **options: Any) -> None:
        from .io._async import write_async

        await write_async(self.root, path, **options)
