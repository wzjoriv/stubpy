"""
The annotation handler table and the :func:`annotation_to_str` dispatcher.
"""
from __future__ import annotations

import ast
import inspect
import re
from collections.abc import Callable
from typing import Any

from stubpy.state.context import StubContext

_TYPING_PREFIX = re.compile(r"(?<![\w.])typing\.")

Predicate = Callable[[Any], bool]
Handler = Callable[[Any, StubContext], str]

ANNOTATION_HANDLERS: list[tuple[Predicate, Handler]] = []


def builtin_handler(predicate: Predicate) -> Callable:
    """Register one of stubpy's own handlers; extensions use :func:`register_annotation_handler`."""
    def decorator(fn: Handler) -> Callable:
        ANNOTATION_HANDLERS.append((predicate, fn))
        return fn
    return decorator


def register_annotation_handler(predicate: Predicate, *, first: bool = False) -> Callable[[Handler], Handler]:
    """Register a custom annotation-to-string handler.

    A handler turns a live annotation object into stub text.  By default it
    runs after every built-in handler, so it only sees annotations none of
    them matched; ``first=True`` puts it ahead of all registered handlers.

    Parameters
    ----------
    predicate : callable
        ``predicate(annotation) -> bool``; ``True`` for the annotations the
        handler renders.
    first : bool, default False
        Try this handler before every other one.

    Returns
    -------
    callable
        A decorator that registers ``handler(annotation, ctx) -> str`` and
        returns it unchanged.

    Examples
    --------
    ::

        from stubpy.extend import annotation_to_str, register_annotation_handler

        @register_annotation_handler(lambda a: isinstance(a, Validated))
        def _validated(annotation, ctx):
            return f"Validated[{annotation_to_str(annotation.inner_type, ctx)}]"
    """
    def decorator(fn: Handler) -> Handler:
        if first:
            ANNOTATION_HANDLERS.insert(0, (predicate, fn))
        else:
            ANNOTATION_HANDLERS.append((predicate, fn))
        return fn
    return decorator


def annotation_to_str(annotation: Any, ctx: StubContext) -> str:
    """Render a live annotation object as stub text.

    Empty sentinels give ``""``; a registered alias wins; then the first
    matching handler; otherwise ``str(annotation)`` without ``typing.``,
    or ``""`` when that is not an expression (an object's ``<...>`` repr).

    Examples
    --------
    >>> from typing import List
    >>> annotation_to_str(List[int], StubContext())
    'List[int]'
    """
    if annotation is inspect.Parameter.empty or annotation is inspect.Signature.empty:
        return ""

    alias = ctx.lookup_alias(annotation)
    if alias is not None:
        return alias

    for predicate, handler in ANNOTATION_HANDLERS:
        try:
            if predicate(annotation):
                return handler(annotation, ctx)
        except Exception:
            pass

    text = _TYPING_PREFIX.sub("", str(annotation))
    return text if _parses(text) else ""


def _parses(text: str) -> bool:
    """``True`` when *text* is a Python expression (not a ``<function ...>`` repr)."""
    try:
        ast.parse(text, mode="eval")
    except SyntaxError:
        return False
    return True
