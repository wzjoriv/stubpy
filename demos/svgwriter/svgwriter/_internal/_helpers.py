"""Method decorators, a name registry and id generation."""

from __future__ import annotations

import functools
import itertools
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Any, Concatenate, Generic, TypeVar, overload

from ._typing import ElementId, P

__all__ = ["Registry", "chainable", "hybridmethod", "next_id"]

T = TypeVar("T")
S = TypeVar("S")


class Registry(Generic[T]):
    """Ordered name -> object mapping populated by a decorator."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str) -> Callable[[T], T]:
        def decorate(item: T) -> T:
            if name in self._items:
                raise ValueError(f"{self.kind} {name!r} is already registered")
            self._items[name] = item
            return item

        return decorate

    def get(self, name: str) -> T:
        return self._items[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)


def chainable(method: Callable[Concatenate[S, P], object]) -> Callable[Concatenate[S, P], S]:
    """Make *method* return ``self`` so calls can be chained."""

    @functools.wraps(method)
    def wrapper(self: S, /, *args: P.args, **kwargs: P.kwargs) -> S:
        method(self, *args, **kwargs)
        return self

    return wrapper


class hybridmethod(Generic[S, P]):
    """A chainable method usable on an instance or, starting fresh, on the class."""

    __slots__ = ("__dict__", "func")

    def __init__(self, func: Callable[Concatenate[S, P], object]) -> None:
        self.func = func
        functools.update_wrapper(self, func)  # type: ignore[arg-type]

    @overload
    def __get__(self, obj: None, owner: type[S]) -> Callable[P, S]: ...
    @overload
    def __get__(self, obj: S, owner: type[S] | None = None) -> Callable[P, S]: ...
    def __get__(self, obj: S | None, owner: type[S] | None = None) -> Callable[P, S]:
        func = self.func

        @functools.wraps(func)
        def bound(*args: P.args, **kwargs: P.kwargs) -> S:
            target: Any = obj if obj is not None else owner()  # type: ignore[misc]
            func(target, *args, **kwargs)
            return target  # type: ignore[no-any-return]

        return bound


class IdFactory:
    """Hand out ``prefix-N`` ids, counting per prefix."""

    __slots__ = ("_counters",)

    def __init__(self) -> None:
        self._counters: defaultdict[str, Iterator[int]] = defaultdict(lambda: itertools.count(1))

    def __call__(self, prefix: str) -> ElementId:
        return ElementId(f"{prefix}{next(self._counters[prefix])}")


next_id = IdFactory()
