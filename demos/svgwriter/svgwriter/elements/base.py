"""The ``Element`` base class and the element registry."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeAlias, TypeVar, Union, overload

from .._internal._helpers import chainable, next_id
from .._internal._typing import ElementId
from ..attributes.values import IRI, DEFAULT_PRECISION, FuncIRI, format_value, svg_name
from ._categories import Category, ContentModel
from ._compose import Composable

if TYPE_CHECKING:
    from .._internal._typing import AnyPath
    from ..attributes.protocols import TextSink

__all__ = [
    "AttrValue",
    "Category",
    "Child",
    "ContentModel",
    "Element",
]

E = TypeVar("E", bound="Element")
T = TypeVar("T")
C = TypeVar("C", "Element", str)

AttrValue = Any
Child: TypeAlias = Union["Element", str]

HREF_ATTRIBUTES: Final = frozenset({"xlink:href"})
_XML_NAME_RE: Final = re.compile(r"^[A-Za-z_][\w.\-]*$")


class Element(Composable):
    """Base class for every SVG element.

    Attributes are kept in ``attributes`` under their SVG names; keyword
    arguments use Python spelling (``stroke_width``, ``class_``) and are
    translated by :func:`svg_name`.
    """

    tag: ClassVar[str] = ""
    category: ClassVar[Category] = Category.OTHER
    content: ClassVar[ContentModel] = ContentModel.ELEMENTS
    _registry: ClassVar[dict[str, type[Element]]] = {}

    def __init_subclass__(
        cls,
        *,
        tag: str | None = None,
        category: Category | None = None,
        content: ContentModel | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if category is not None:
            cls.category = category
        if content is not None:
            cls.content = content
        if tag is not None:
            cls.tag = tag
            Element._registry[tag] = cls

    def __init__(
        self,
        *children: Child,
        id: str | None = None,
        attrs: Mapping[str, AttrValue] | None = None,
        **extra: AttrValue,
    ) -> None:
        self.attributes: dict[str, AttrValue] = {}
        self.children: list[Child] = []
        self.parent: Element | None = None
        if id is not None:
            self.id = id
        for name, value in (attrs or {}).items():
            self.set(name, value)
        self.update(**extra)
        self.extend(children)

    @classmethod
    def registered(cls, category: Category | None = None) -> dict[str, type[Element]]:
        """Registered element classes, optionally filtered by category."""
        return {
            tag: klass for tag, klass in cls._registry.items() if category is None or klass.category is category
        }

    @property
    def id(self) -> str | None:
        value = self.attributes.get("id")
        return None if value is None else str(value)

    @id.setter
    def id(self, value: str | None) -> None:
        if value is None:
            self.attributes.pop("id", None)
            return
        if not _XML_NAME_RE.match(value):
            raise ValueError(f"invalid id: {value!r}")
        self.attributes = {"id": value, **{k: v for k, v in self.attributes.items() if k != "id"}}

    def ensure_id(self) -> ElementId:
        """Return the id, assigning a generated one if needed."""
        if self.id is None:
            self.id = next_id(self.tag or "el")
        return ElementId(self.id or "")

    @property
    def ref(self) -> FuncIRI:
        """``url(#id)`` for this element, assigning an id if needed."""
        return FuncIRI("#" + self.ensure_id())

    @property
    def href(self) -> IRI:
        """``#id`` for this element, assigning an id if needed."""
        return IRI.local(self.ensure_id())

    @chainable
    def set(self, name: str, value: AttrValue) -> None:
        """Set one attribute; ``None`` removes it."""
        key = svg_name(name)
        if value is None:
            self.attributes.pop(key, None)
            return
        if isinstance(value, Element):
            value = value.href if key in HREF_ATTRIBUTES else value.ref
        self.attributes[key] = value

    @chainable
    def update(self, attributes: Mapping[str, AttrValue] | None = None, /, **kwargs: AttrValue) -> None:
        """Set several attributes; ``None`` values are skipped."""
        for name, value in {**(attributes or {}), **kwargs}.items():
            if value is not None:
                self.set(name, value)

    @overload
    def get(self, name: str) -> AttrValue | None: ...
    @overload
    def get(self, name: str, default: T) -> AttrValue | T: ...
    def get(self, name: str, default: object = None) -> object:
        return self.attributes.get(svg_name(name), default)

    def discard(self, name: str) -> None:
        self.attributes.pop(svg_name(name), None)

    def append(self, child: C) -> C:
        """Append a child element or text node and return it."""
        if isinstance(child, str):
            if ContentModel.TEXT not in self.content:
                raise TypeError(f"<{self.tag}> cannot contain text")
        elif isinstance(child, Element):
            if child.parent is not None:
                child.parent.remove(child)
            child.parent = self
        else:
            raise TypeError(f"cannot append {type(child).__name__}")
        self.children.append(child)
        return child

    def extend(self, children: Iterable[Child]) -> None:
        for child in children:
            self.append(child)

    def insert(self, index: int, child: C) -> C:
        self.append(child)
        self.children.insert(index, self.children.pop())
        return child

    def remove(self, child: Child) -> None:
        self.children.remove(child)
        if isinstance(child, Element):
            child.parent = None

    def __len__(self) -> int:
        return len(self.children)

    def __iter__(self) -> Iterator[Element]:
        return (c for c in self.children if isinstance(c, Element))

    def __bool__(self) -> bool:
        return True

    def iter(self, tag: str | None = None) -> Iterator[Element]:
        """Depth-first walk over this element and its descendants."""
        if tag is None or self.tag == tag:
            yield self
        for child in self:
            yield from child.iter(tag)

    @overload
    def find(self, match: type[E]) -> E | None: ...
    @overload
    def find(self, match: str) -> Element | None: ...
    def find(self, match: type[Element] | str) -> Element | None:
        """First descendant (or self) matching a tag or class."""
        return next(iter(self.find_all(match)), None)

    @overload
    def find_all(self, match: type[E]) -> list[E]: ...
    @overload
    def find_all(self, match: str) -> list[Element]: ...
    def find_all(self, match: type[Element] | str) -> list[Element]:
        if isinstance(match, str):
            return list(self.iter(match))
        return [e for e in self.iter() if isinstance(e, match)]

    def root(self) -> Element:
        node = self
        while node.parent is not None:
            node = node.parent
        return node

    def copy(self: E) -> E:
        """Deep copy, detached from any parent."""
        clone = type(self).__new__(type(self))
        clone.__dict__.update(self.__dict__)
        clone.attributes = dict(self.attributes)
        clone.parent = None
        clone.children = []
        for child in self.children:
            clone.children.append(child if isinstance(child, str) else child.copy())
            if isinstance(child, Element):
                clone.children[-1].parent = clone  # type: ignore[union-attr]
        return clone

    def to_string(self, **options: Any) -> str:
        """Serialize; see :class:`svgwriter.io.SerializeOptions`."""
        from ..io.writer import to_string

        return to_string(self, **options)

    def save(self, target: AnyPath | TextSink, **options: Any) -> None:
        """Write to a path or text stream."""
        from ..io.writer import write

        write(self, target, **options)

    def __str__(self) -> str:
        return self.to_string(xml_declaration=False, pretty=False)

    def __repr__(self) -> str:
        shown = " ".join(f"{k}={format_value(v)!r}" for k, v in list(self.attributes.items())[:3])
        return f"<{type(self).__name__} {self.tag}{' ' + shown if shown else ''}>"


@format_value.register(Element)
def _format_element(value: Element, precision: int = DEFAULT_PRECISION) -> str:
    return value.ref.svg_value(precision)
