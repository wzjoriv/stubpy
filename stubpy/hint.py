"""Decorators that tell stubpy what introspection cannot see.

Each decorator only sets an attribute on the decorated object and returns
it unchanged, so the cost at runtime is one attribute assignment.  stubpy
also recognises the decorators in the source, so they work without importing
the module and on objects that do not accept attributes; they never appear in the
generated stub.

Examples
--------
::

    from stubpy import hint

    @hint.signature("(x: float, y: float) -> float")   # JIT, C or dynamically built callables
    @numba.njit
    def dist(x, y): ...

    @hint.returns("np.ndarray")                        # keep the parameters, fix the return type
    def load(path): ...

    @hint.ignore                                       # never stubbed
    def _debug_dump(): ...

To keep stubpy a development-only dependency, fall back to no-op decorators::

    try:
        from stubpy import hint
    except ImportError:
        class hint:
            signature = returns = staticmethod(lambda _text: lambda obj: obj)
            ignore = staticmethod(lambda obj: obj)
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from ._constants import HINT_IGNORE_ATTR, HINT_RETURNS_ATTR, HINT_SIGNATURE_ATTR

__all__ = ["ignore", "returns", "signature"]

T = TypeVar("T")


def signature(text: str) -> Callable[[T], T]:
    """Replace the stub signature of a function or method.

    Parameters
    ----------
    text : str
        Everything that follows the name in the ``def`` line: the
        parenthesised parameters and, optionally, ``-> return``.  Methods
        include ``self`` / ``cls``, e.g. ``"(self, x: int) -> str"``.

    Returns
    -------
    callable
        A decorator that records *text* and returns its argument unchanged.

    Raises
    ------
    TypeError
        If *text* is not a string.
    ValueError
        If *text* does not start with ``(``.

    Examples
    --------
    >>> @signature("(x: float) -> float")
    ... def square(x):
    ...     return x * x
    >>> square(3)
    9
    """
    if not isinstance(text, str):
        raise TypeError(f"hint.signature() takes a string, not {type(text).__name__}")
    if not text.strip().startswith("("):
        raise ValueError(f"hint.signature() text must start with '(': {text!r}")
    return _setter(HINT_SIGNATURE_ATTR, text.strip())


def returns(annotation: str) -> Callable[[T], T]:
    """Replace only the return annotation in the stub.

    Parameters
    ----------
    annotation : str
        The return type as it should appear in the stub, e.g. ``"list[int]"``.

    Returns
    -------
    callable
        A decorator that records *annotation* and returns its argument unchanged.

    Raises
    ------
    TypeError
        If *annotation* is not a string.

    Examples
    --------
    >>> @returns("list[int]")
    ... def evens(n):
    ...     return list(range(0, n, 2))
    >>> evens(5)
    [0, 2, 4]
    """
    if not isinstance(annotation, str):
        raise TypeError(f"hint.returns() takes a string, not {type(annotation).__name__}")
    return _setter(HINT_RETURNS_ATTR, annotation.strip())


def ignore(obj: T) -> T:
    """Leave a function, method or class out of the stub.

    Examples
    --------
    >>> @ignore
    ... def _debug_dump():
    ...     pass
    >>> _debug_dump.__stubpy_ignore__
    True
    """
    _mark(obj, HINT_IGNORE_ATTR, True)
    return obj


def _setter(attr: str, value: Any) -> Callable[[T], T]:
    def decorator(obj: T) -> T:
        _mark(obj, attr, value)
        return obj
    return decorator


def _mark(obj: Any, attr: str, value: Any) -> None:
    """Set *attr* on *obj*; objects without writable attributes are left alone (the source still carries the hint)."""
    try:
        setattr(obj, attr, value)
    except (AttributeError, TypeError):
        pass
