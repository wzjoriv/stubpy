"""The annotation handler table and the :func:`annotation_to_str` dispatcher."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from stubpy.core.context import StubContext

Predicate = Callable[[Any], bool]
Handler = Callable[[Any, StubContext], str]

ANNOTATION_HANDLERS: list[tuple[Predicate, Handler]] = []


def builtin_handler(predicate: Predicate) -> Callable:
    """Register one of stubpy's own handlers; extensions use :func:`register_annotation_handler`."""
    def decorator(fn: Handler) -> Callable:
        ANNOTATION_HANDLERS.append((predicate, fn))
        return fn
    return decorator


def register_annotation_handler(predicate: Predicate) -> Callable:
    """Register a custom annotation-to-string handler.

    Handlers run in registration order after all built-in handlers, so a
    custom handler only sees annotations no built-in one matched.  To run
    before them, insert into ``stubpy._ANN_HANDLERS`` at index 0.

    Parameters
    ----------
    predicate : callable
        Returns ``True`` for the annotation objects the handler renders.

    Returns
    -------
    callable
        A decorator that registers ``handler(annotation, ctx) -> str`` and
        returns it unchanged.

    Examples
    --------
    ::

        from stubpy import register_annotation_handler
        from stubpy.emit.annotations import annotation_to_str

        @register_annotation_handler(lambda a: isinstance(a, Validated))
        def _handle_validated(annotation, ctx):
            return f"Validated[{annotation_to_str(annotation.inner_type, ctx)}]"
    """
    def decorator(fn: Handler) -> Callable:
        ANNOTATION_HANDLERS.append((predicate, fn))
        return fn
    return decorator


def annotation_to_str(annotation: Any, ctx: StubContext) -> str:
    """Render a live annotation object as stub text.

    Empty sentinels give ``""``; a registered alias wins; then the first
    matching handler; otherwise ``str(annotation)`` without ``typing.``.

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

    return str(annotation).replace("typing.", "")
