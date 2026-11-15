"""Typed child lists, composition operators and nestable containers."""

from __future__ import annotations

import weakref
from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager
from types import TracebackType
from typing import TYPE_CHECKING, Generic, TypeVar, overload

from .._internal._typing import Self, Stack
from ._factory import ElementFactory
from .base import Element

if TYPE_CHECKING:
    from ..attributes.values import FuncIRI
    from .structure import Defs

__all__ = ["ChildT", "Container", "GraphicsContainer", "Insertable"]

ChildT = TypeVar("ChildT", bound=Element)
E = TypeVar("E", bound=Element)

Insertable = Element | str | Iterable[Element]

_CURSORS: weakref.WeakKeyDictionary[Element, Stack[Element]] = weakref.WeakKeyDictionary()


def attach_cursor(element: Element, stack: Stack[Element] | None) -> None:
    """Let ``with element:`` move *stack*'s insertion point."""
    if stack is not None:
        _CURSORS[element] = stack


def cursor_of(element: Element) -> Stack[Element] | None:
    return _CURSORS.get(element)


def flatten(items: Insertable) -> list[Element | str]:
    """One element, a text run or an iterable of elements, as a list."""
    if isinstance(items, (Element, str)):
        return [items]
    try:
        flat = list(items)
    except TypeError:
        raise TypeError(f"expected an element or an iterable of elements, got {type(items).__name__}") from None
    for item in flat:
        if not isinstance(item, Element):
            raise TypeError(f"expected elements, got {type(item).__name__}")
    return flat  # type: ignore[return-value]


class Container(Element, Generic[ChildT]):
    """Adds typed ``add``/iteration and ``+=`` for elements with a known child type."""

    def add(self, child: ChildT) -> ChildT:
        return self.append(child)

    def __iadd__(self, children: ChildT | Iterable[ChildT]) -> Self:
        """``container += child`` or ``container += [a, b]`` appends."""
        self.extend(flatten(children))
        return self

    def __iter__(self) -> Iterator[ChildT]:
        return (c for c in self.children if isinstance(c, Element))  # type: ignore[misc]

    @overload
    def __getitem__(self, index: int) -> ChildT: ...
    @overload
    def __getitem__(self, index: slice) -> list[ChildT]: ...
    def __getitem__(self, index: int | slice) -> ChildT | list[ChildT]:
        return list(self)[index]


class GraphicsContainer(  # type: ignore[misc]
    ElementFactory,
    AbstractContextManager["GraphicsContainer", None],
    Container[Element],
):
    """Containers of drawable content: shortcuts, ``with`` nesting and ``%``.

    ``container % element`` puts *element* into ``<defs>`` (once) and
    returns its ``url(#id)``; ``container %= element`` does the same and
    keeps the container.
    """

    def _place(self, element: E) -> E:
        attach_cursor(element, cursor_of(self))
        return self.append(element)

    def _define(self, element: E) -> E:
        element.ensure_id()
        defs = self.definitions()
        if element.parent is not defs:
            defs.append(element)
        attach_cursor(element, cursor_of(self))
        return element

    def definitions(self) -> Defs:
        """The root ``<svg>``'s ``<defs>``, or one of this container."""
        from .structure import Defs, Svg

        root = self.root()
        if isinstance(root, Svg):
            return root.defs()
        if isinstance(self, Defs):
            return self
        for child in self:
            if isinstance(child, Defs):
                return child
        return self.insert(0, Defs())

    def __mod__(self, element: Element) -> FuncIRI:
        if not isinstance(element, Element):
            return NotImplemented
        return self._define(element).ref

    def __imod__(self, elements: Element | Iterable[Element]) -> Self:
        for element in flatten(elements):
            self._define(element)  # type: ignore[type-var]
        return self

    def __enter__(self) -> Self:
        stack = cursor_of(self)
        if stack is not None:
            stack.push(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        stack = cursor_of(self)
        if stack is not None and stack and stack.peek() is self:
            stack.pop()
