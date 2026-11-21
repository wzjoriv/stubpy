"""A tiny typed LIFO stack (pre-3.12 spelling)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Generic, TypeVar

__all__ = ["Stack"]

T = TypeVar("T")


class Stack(Generic[T]):
    """LIFO stack used to track the current insertion parent."""

    __slots__ = ("_items",)

    def __init__(self, items: Iterable[T] = ()) -> None:
        self._items: list[T] = list(items)

    def push(self, item: T) -> T:
        self._items.append(item)
        return item

    def pop(self) -> T:
        return self._items.pop()

    def peek(self) -> T:
        return self._items[-1]

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __iter__(self) -> Iterator[T]:
        return reversed(self._items)
