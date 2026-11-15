"""Name registries and method decorators."""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from typing import Concatenate, Generic, TypeVar

from ._typing import P

__all__ = ["Registry", "chainable"]

T = TypeVar("T")
S = TypeVar("S")


class Registry(Generic[T]):
    """Ordered name -> object mapping populated by a decorator."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, T] = {}

    def add(self, name: str, item: T) -> T:
        if name in self._items:
            raise ValueError(f"{self.kind} {name!r} is already registered")
        self._items[name] = item
        return item

    def register(self, name: str) -> Callable[[T], T]:
        def decorate(item: T) -> T:
            return self.add(name, item)

        return decorate

    def get(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"unknown {self.kind} {name!r}") from None

    def names(self) -> list[str]:
        return list(self._items)

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


def chainable(method: Callable[Concatenate[S, P], object]) -> Callable[Concatenate[S, P], S]:
    """Make *method* return ``self`` so calls can be chained."""

    @functools.wraps(method)
    def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> S:
        method(self, *args, **kwargs)
        return self

    return wrapper
