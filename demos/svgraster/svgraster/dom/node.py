"""The element tree the renderer walks."""
from __future__ import annotations

from collections.abc import Iterator

from .style import computed_style
from .units import DEFAULT_FONT_SIZE, UnitContext


class Node:
    """An SVG element with its attributes, specified and computed style."""

    __slots__ = ("tag", "attrs", "children", "parent", "text", "tail", "specified", "style", "font_size")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None, parent: Node | None = None,
                 text: str = "", tail: str = ""):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children: list[Node] = []
        self.parent = parent
        self.text = text
        self.tail = tail
        self.specified: dict[str, str] = {}
        self.style: dict[str, str] = {}
        self.font_size = DEFAULT_FONT_SIZE

    def __repr__(self) -> str:
        ident = f" id={self.id!r}" if self.id else ""
        return f"<Node {self.tag}{ident} children={len(self.children)}>"

    @property
    def id(self) -> str | None:
        """The ``id`` attribute."""
        return self.attrs.get("id")

    @property
    def classes(self) -> frozenset[str]:
        """The ``class`` attribute as a set."""
        return frozenset(self.attrs.get("class", "").split())

    @property
    def href(self) -> str | None:
        """The ``href`` / ``xlink:href`` attribute."""
        return self.attrs.get("href")

    def get(self, name: str, default: str | None = None) -> str | None:
        """An attribute value."""
        return self.attrs.get(name, default)

    def iter(self) -> Iterator[Node]:
        """Depth-first iteration including ``self``."""
        yield self
        for child in self.children:
            yield from child.iter()

    def ancestors(self) -> Iterator[Node]:
        """Parents from nearest to root."""
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def units(self, viewport: tuple[float, float]) -> UnitContext:
        """A unit context for this element's lengths."""
        return UnitContext(self.font_size, viewport[0], viewport[1])

    def recompute_style(self, parent: Node | None) -> None:
        """Recompute this subtree's computed style below ``parent``."""
        parent_style = parent.style if parent is not None else None
        parent_font = parent.font_size if parent is not None else DEFAULT_FONT_SIZE
        self.style, self.font_size = computed_style(self.specified, parent_style, parent_font)
        for child in self.children:
            child.recompute_style(self)

    def clone(self, parent: Node | None) -> Node:
        """A deep copy attached to ``parent`` with styles recomputed."""
        copy = self._copy(parent)
        copy.recompute_style(parent)
        return copy

    def _copy(self, parent: Node | None) -> Node:
        copy = Node(self.tag, self.attrs, parent, self.text, self.tail)
        copy.specified = self.specified
        copy.children = [child._copy(copy) for child in self.children]
        return copy
