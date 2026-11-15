"""``Document``: a root ``<svg>`` plus a cursor for nested building."""

from __future__ import annotations

import enum
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path as FilePath
from typing import TYPE_CHECKING, Any, TypeVar

from ._internal._typing import AnyPath, Self, Stack
from .elements._factory import ElementFactory
from .elements.base import Element
from .elements.container import attach_cursor, flatten
from .elements.shapes import Circle, Ellipse, Line, Path, Polygon, Polyline, Rect, Shape
from .elements.structure import Defs, Desc, Svg, Title
from .video.animation import DEFAULT_FPS

if TYPE_CHECKING:
    from .attributes.protocols import TextSink
    from .attributes.reference import FuncIRI
    from .attributes.style import StyleSheet
    from .elements.structure import StyleElement
    from .io.parser import Strictness
    from .video.animation import Renderer, Update

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


class Document(ElementFactory):
    """An SVG document under construction.

    Shortcut methods (``doc.circle(...)``, ``doc.linear_gradient(...)``)
    build an element, add it and return it; definitions go into ``<defs>``.
    Containers returned by shortcuts nest when used with ``with``.

    Parameters
    ----------
    width, height : float, optional
        Canvas size; a matching ``viewBox`` is added unless one is given.
    root : Svg, optional
        Use an existing root instead of creating one.
    **kwargs
        Forwarded to :class:`~svgwriter.elements.Svg`.

    Notes
    -----
    ``doc += element`` (or a list) adds at the insertion point.
    ``doc % element`` puts *element* into ``<defs>`` once and returns its
    ``url(#id)``; ``doc %= element`` does the same and keeps ``doc``.

    Examples
    --------
    >>> doc = Document(100, 100)
    >>> glow = doc.radial_gradient(cx=0.5, cy=0.5, r=0.5)
    >>> with doc.group(fill="red") as g:
    ...     _ = doc.rect(10, 10, 20, 20)
    ...     _ = doc.circle(50, 50, 10, fill=glow)
    >>> len(g)
    2
    >>> doc += Rect(0, 0, 5, 5)
    >>> doc.root[-1].tag
    'rect'
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

    def define(self, element: E) -> E:
        """Put *element* in ``<defs>`` (giving it an id) and return it."""
        return self._define(element)

    def title(self, text: str) -> Title:
        return self.root.insert(0, Title(text))

    def describe(self, text: str) -> Desc:
        return self.add(Desc(text))

    def style(self, css: str | StyleSheet = "", **kwargs: Any) -> StyleElement:
        """Add a ``<style>`` sheet near the top of the document."""
        from .elements.structure import StyleElement

        return self.root.insert(1 if self.root.children and isinstance(self.root.children[0], Title) else 0, StyleElement(css, **kwargs))

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
            size = kwargs.pop("size")
            shape: Shape = Rect.square(size, **kwargs)
        elif kind in (ShapeKind.POLYLINE, ShapeKind.POLYGON):
            points = kwargs.pop("points", ())
            shape = Polygon(points, **kwargs) if kind is ShapeKind.POLYGON else Polyline(points, **kwargs)
        else:
            classes: dict[ShapeKind, type[Shape]] = {
                ShapeKind.RECT: Rect,
                ShapeKind.CIRCLE: Circle,
                ShapeKind.ELLIPSE: Ellipse,
                ShapeKind.LINE: Line,
                ShapeKind.PATH: Path,
            }
            shape = classes[kind](**kwargs)
        return self.add(shape)

    def __iter__(self) -> Iterator[Element]:
        return self.root.iter()

    def get_element_by_id(self, element_id: str) -> Element | None:
        return self.root.get_element_by_id(element_id)

    def to_string(self, **options: Any) -> str:
        return self.root.to_string(**options)

    def __str__(self) -> str:
        return self.root.to_string(xml_declaration=False)

    def _repr_svg_(self) -> str:
        return self.root.to_string(xml_declaration=False)

    def save(self, target: AnyPath | TextSink, **options: Any) -> None:
        self.root.save(target, **options)

    async def save_async(self, path: AnyPath, **options: Any) -> None:
        from .io._async import write_async

        await write_async(self.root, path, **options)

    def render_animation(
        self,
        path: AnyPath,
        fps: float = DEFAULT_FPS,
        duration: float | None = None,
        renderer: Renderer | str | None = None,
        *,
        update: Update | None = None,
        ffmpeg: str | None = None,
    ) -> FilePath:
        """Render frames through *renderer* and encode them with ffmpeg.

        See :func:`svgwriter.video.render_animation` for the parameters.
        Raises :class:`~svgwriter.video.FFmpegNotFoundError` before doing
        any work when ffmpeg is missing.
        """
        from .video.animation import render_animation

        return render_animation(self, path, fps, duration, renderer, update=update, ffmpeg=ffmpeg)
