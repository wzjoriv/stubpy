"""``hybridmethod``: a chainable method that also works on the class."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, Concatenate, Generic, TypeVar, overload

from ._typing import P

__all__ = ["hybridmethod"]

S = TypeVar("S")


class hybridmethod(Generic[S, P]):
    """Chainable method usable on an instance or on the class.

    On an instance it appends and returns the instance. On the class it
    starts from a fresh ``cls()``, so ``Transform.rotate(30)`` and
    ``Transform().rotate(30)`` build the same thing.
    """

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
