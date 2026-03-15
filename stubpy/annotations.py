"""
stubpy.annotations
==================

Annotation-to-string conversion using a registered dispatch table.

The central function :func:`annotation_to_str` converts any live Python
annotation object to a stub-safe string. Each annotation *kind* is handled
by a small private function registered via ``@_register(predicate)``. Adding
support for a new annotation type is a single decorated function — no
editing of an ``if/elif`` chain.

Resolution order inside :func:`annotation_to_str`:

1. ``inspect.Parameter.empty`` → ``""``
2. Alias-registry lookup → e.g. ``"types.Length"``
3. Registered dispatch handlers, in registration order
4. Fallback: ``str(annotation).replace("typing.", "")``
"""
from __future__ import annotations

import collections.abc
import inspect
import types as _builtin_types
import typing
from typing import Any, Callable

from .context import StubContext


def get_hints_for_method(fn: Any) -> dict[str, Any]:
    """Safely resolve type hints for *fn*, unwrapping descriptors first.

    Parameters
    ----------
    fn : Any
        A callable, :class:`classmethod`, :class:`staticmethod`, or
        :class:`property`. ``None`` returns an empty dict.

    Returns
    -------
    dict
        ``{param_name: annotation}`` with forward references resolved,
        or an empty dict if resolution fails or *fn* is ``None``.

    Examples
    --------
    >>> class A:
    ...     def foo(self, x: int) -> str: ...
    >>> get_hints_for_method(A.foo)
    {'x': <class 'int'>, 'return': <class 'str'>}
    """
    if fn is None:
        return {}
    raw: Any = fn
    if isinstance(raw, (classmethod, staticmethod)):
        raw = raw.__func__
    elif isinstance(raw, property):
        raw = raw.fget
    try:
        return typing.get_type_hints(raw)
    except Exception:
        return getattr(raw, "__annotations__", {})


def default_to_str(default: Any) -> str:
    """Render a parameter default value as a stub-safe string.

    Parameters
    ----------
    default : Any
        The default value, or ``inspect.Parameter.empty`` when the
        parameter has no default.

    Returns
    -------
    str
        ``repr(default)`` for real defaults, or ``""`` for the empty
        sentinel.

    Examples
    --------
    >>> import inspect
    >>> default_to_str(inspect.Parameter.empty)
    ''
    >>> default_to_str("black")
    "'black'"
    >>> default_to_str(1.0)
    '1.0'
    >>> default_to_str(None)
    'None'
    """
    if default is inspect.Parameter.empty:
        return ""
    return repr(default)


# ---------------------------------------------------------------------------
# Dispatch table — private implementation detail
# ---------------------------------------------------------------------------

_ANN_HANDLERS: list[tuple[
    Callable[[Any], bool],
    Callable[[Any, StubContext], str],
]] = []


def _register(predicate: Callable[[Any], bool]) -> Callable:
    """Register an annotation handler for all annotations matching *predicate*.

    Decorates a ``(annotation, ctx) -> str`` function and appends it to
    the dispatch table. Handlers are tried in registration order; the
    first whose predicate returns ``True`` wins.

    Parameters
    ----------
    predicate : callable
        A callable that takes an annotation object and returns ``True``
        if the decorated handler should process it.

    Returns
    -------
    callable
        A decorator that registers and returns the decorated function.
    """
    def decorator(fn: Callable[[Any, StubContext], str]) -> Callable:
        _ANN_HANDLERS.append((predicate, fn))
        return fn
    return decorator


@_register(lambda a: isinstance(a, str))
def _handle_str_forward_ref(annotation: Any, ctx: StubContext) -> str:
    """Handle string forward references such as ``"Element"`` or ``'Element'``."""
    return annotation.strip("'\"")


@_register(lambda a: isinstance(a, typing.ForwardRef))
def _handle_forward_ref(annotation: Any, ctx: StubContext) -> str:
    """Handle :class:`typing.ForwardRef` objects from the typing machinery."""
    return annotation.__forward_arg__


@_register(lambda a: a is type(None))
def _handle_none_type(annotation: Any, ctx: StubContext) -> str:
    """Handle ``NoneType`` — emits the literal string ``"None"``."""
    return "None"


@_register(lambda a: isinstance(a, _builtin_types.UnionType))
def _handle_pep604_union(annotation: Any, ctx: StubContext) -> str:
    """Handle PEP 604 ``X | Y`` union types (Python 3.10+).

    ``str | None`` collapses to ``Optional[str]`` for compatibility with
    older type checkers.
    """
    parts = [annotation_to_str(a, ctx) for a in annotation.__args__]
    non_none = [p for p in parts if p != "None"]
    has_none = len(parts) != len(non_none)
    if has_none and len(non_none) == 1:
        return f"Optional[{non_none[0]}]"
    return " | ".join(parts)


@_register(lambda a: isinstance(a, type))
def _handle_plain_type(annotation: Any, ctx: StubContext) -> str:
    """Handle plain class objects using ``__name__``."""
    return annotation.__name__


@_register(lambda a: getattr(a, "__origin__", None) is not None)
def _handle_generic(annotation: Any, ctx: StubContext) -> str:
    """Handle all subscripted :mod:`typing` generics via ``__origin__``.

    Covers Union, Optional, Callable, Literal, and container generics
    such as ``List[str]``, ``Dict[str, int]``, ``Tuple[float, float]``.
    """
    origin = annotation.__origin__

    if origin is typing.Union:
        args = annotation.__args__
        if not args:
            return "Union"
        none_type = type(None)
        non_none = [a for a in args if a is not none_type]
        has_none = any(a is none_type for a in args)
        if has_none and len(non_none) == 1:
            return f"Optional[{annotation_to_str(non_none[0], ctx)}]"
        parts = [annotation_to_str(a, ctx) for a in args]
        return f"Union[{', '.join(parts)}]"

    if origin is collections.abc.Callable:
        args = annotation.__args__
        if not args:
            return "Callable"
        *param_types, ret_type = args
        ret_str = annotation_to_str(ret_type, ctx)
        if param_types and param_types[0] is not None:
            params_str = (
                "[" + ", ".join(annotation_to_str(p, ctx) for p in param_types) + "]"
            )
        else:
            params_str = "[]"
        return f"Callable[{params_str}, {ret_str}]"

    if origin is typing.Literal:
        args = annotation.__args__
        if not args:
            return "Literal"
        return f"Literal[{', '.join(repr(a) for a in args)}]"

    origin_name: str = (
        getattr(annotation, "_name", None)
        or getattr(origin, "__name__", None)
        or str(origin).replace("typing.", "")
    )
    args = getattr(annotation, "__args__", None)
    if args:
        args_str = ", ".join(annotation_to_str(a, ctx) for a in args)
        return f"{origin_name}[{args_str}]"
    return origin_name


@_register(lambda a: getattr(a, "_name", None) is not None)
def _handle_bare_typing_alias(annotation: Any, ctx: StubContext) -> str:
    """Handle bare unsubscripted typing aliases such as ``List``, ``Dict``."""
    return annotation._name  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def annotation_to_str(annotation: Any, ctx: StubContext) -> str:
    """Convert any annotation object to a valid ``.pyi`` string.

    Resolution order:

    1. ``inspect.Parameter.empty`` or ``inspect.Signature.empty`` → ``""``
    2. Alias-registry lookup via :meth:`~stubpy.context.StubContext.lookup_alias` —
       if the annotation matches a registered alias it is returned as-is
       (e.g. ``"types.Length"``) and the alias module is marked as used.
    3. Registered dispatch handlers, tried in order.
    4. Fallback: ``str(annotation).replace("typing.", "")``.

    This function is recursive — generic argument lists are processed by
    calling it on each ``__args__`` element.

    Parameters
    ----------
    annotation : Any
        Any live Python annotation object. Accepted values include plain
        types (``int``, ``str``), PEP 604 unions (``str | None``),
        subscripted typing generics (``Optional[int]``), string forward
        references (``"Element"``), :class:`typing.ForwardRef` objects,
        ``NoneType``, and ``inspect.Parameter.empty``.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`. Used for alias
        lookup and to track which type-module imports are needed.

    Returns
    -------
    str
        A stub-safe string representation, or ``""`` for empty sentinels.

    See Also
    --------
    format_param : Formats a full parameter including name and default.
    stubpy.context.StubContext.lookup_alias : Alias resolution logic.

    Examples
    --------
    >>> from stubpy.context import StubContext
    >>> from stubpy.annotations import annotation_to_str
    >>> from typing import Optional, List
    >>> ctx = StubContext()
    >>> annotation_to_str(int, ctx)
    'int'
    >>> annotation_to_str(str | None, ctx)
    'Optional[str]'
    >>> annotation_to_str(List[int], ctx)
    'List[int]'
    >>> annotation_to_str("Element", ctx)
    'Element'
    >>> annotation_to_str(type(None), ctx)
    'None'
    """
    if annotation is inspect.Parameter.empty or annotation is inspect.Signature.empty:
        return ""

    alias = ctx.lookup_alias(annotation)
    if alias is not None:
        return alias

    for predicate, handler in _ANN_HANDLERS:
        try:
            if predicate(annotation):
                return handler(annotation, ctx)
        except Exception:
            pass

    return str(annotation).replace("typing.", "")


def format_param(
    param: inspect.Parameter,
    hints: dict[str, Any],
    ctx: StubContext,
) -> str:
    """Format a single :class:`inspect.Parameter` as a stub-ready string.

    The *hints* dict (from :func:`get_hints_for_method`) takes priority
    over ``param.annotation`` because it contains fully resolved
    annotations — forward references evaluated, ``from __future__ import
    annotations`` strings expanded.

    Parameters
    ----------
    param : inspect.Parameter
        The parameter to format.
    hints : dict
        Resolved type hints for the owning function, keyed by parameter
        name. Falls back to ``param.annotation`` when the name is absent.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`, passed through
        to :func:`annotation_to_str`.

    Returns
    -------
    str
        A formatted string such as ``"x: int"``, ``"size: float = 1.0"``,
        ``"*args: str"``, or ``"**kwargs"``.

    Examples
    --------
    >>> import inspect
    >>> from stubpy.context import StubContext
    >>> from stubpy.annotations import format_param
    >>> ctx = StubContext()
    >>> p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ...                        annotation=int, default=0)
    >>> format_param(p, {}, ctx)
    'x: int = 0'
    >>> p_star = inspect.Parameter("items", inspect.Parameter.VAR_POSITIONAL,
    ...                             annotation=str)
    >>> format_param(p_star, {"items": str}, ctx)
    '*items: str'
    """
    name = param.name
    ann = hints.get(name, param.annotation)
    ann_str = annotation_to_str(ann, ctx)
    default_str = default_to_str(param.default)

    if param.kind == inspect.Parameter.VAR_POSITIONAL:
        return f"*{name}" + (f": {ann_str}" if ann_str else "")
    if param.kind == inspect.Parameter.VAR_KEYWORD:
        return f"**{name}" + (f": {ann_str}" if ann_str else "")

    result = name
    if ann_str:
        result += f": {ann_str}"
    if default_str:
        result += f" = {default_str}"
    return result
