"""A typed child-list mixin."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Generic, TypeVar, overload

from .base import Element

__all__ = ["ChildT", "Container"]

ChildT = TypeVar("ChildT", bound=Element)


class Container(Element, Generic[ChildT]):
    """Adds typed ``add``/iteration for elements with a known child type."""

    def add(self, child: ChildT) -> ChildT:
        return self.append(child)

    def add_all(self, children: Iterable[ChildT]) -> list[ChildT]:
        return [self.append(child) for child in children]

    def __iter__(self) -> Iterator[ChildT]:
        return (c for c in self.children if isinstance(c, Element))  # type: ignore[misc]

    @overload
    def __getitem__(self, index: int) -> ChildT: ...
    @overload
    def __getitem__(self, index: slice) -> list[ChildT]: ...
    def __getitem__(self, index: int | slice) -> ChildT | list[ChildT]:
        items = list(self)
        return items[index]
