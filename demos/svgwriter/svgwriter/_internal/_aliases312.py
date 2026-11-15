"""PEP 695 spellings of shared aliases. Imported only on Python 3.12+."""

from collections.abc import Iterable, Iterator

__all__ = ["Matrix6", "Pair", "Stack", "first"]

type Pair[T] = tuple[T, T]
type Matrix6 = tuple[float, float, float, float, float, float]


class Stack[T]:
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


def first[T](items: Iterable[T], default: T) -> T:
    """Return the first item of *items*, or *default* when empty."""
    for item in items:
        return item
    return default
