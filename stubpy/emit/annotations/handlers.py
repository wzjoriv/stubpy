"""Built-in annotation handlers, registered in dispatch order on import."""
from __future__ import annotations

import collections.abc
import types as _builtin_types
import typing
from typing import Any

from stubpy.core.context import StubContext

from .registry import annotation_to_str, builtin_handler

_UnionType = getattr(_builtin_types, "UnionType", None)

_TYPEVAR_LIKE_TYPES: tuple[type, ...] = tuple(
    cls for cls in (
        getattr(typing, "TypeVar", None),
        getattr(typing, "ParamSpec", None),
        getattr(typing, "TypeVarTuple", None),
    )
    if cls is not None
)


def _optional_alias(non_none: list[Any], ctx: StubContext, modern: bool) -> str | None:
    """Render ``Alias | None`` when the non-``None`` members rebuild a registered alias."""
    try:
        rebuilt = non_none[0]
        for t in non_none[1:]:
            rebuilt = rebuilt | t
        alias = ctx.lookup_alias(rebuilt)
        if alias:
            return f"{alias} | None" if modern else f"Optional[{alias}]"
    except Exception:
        pass
    return None


@builtin_handler(lambda a: isinstance(a, str))
def _handle_str_forward_ref(annotation: Any, ctx: StubContext) -> str:
    """String forward references such as ``"Element"``."""
    return annotation.strip("'\"")


@builtin_handler(lambda a: isinstance(a, typing.ForwardRef))
def _handle_forward_ref(annotation: Any, ctx: StubContext) -> str:
    """:class:`typing.ForwardRef` objects."""
    return annotation.__forward_arg__


@builtin_handler(lambda a: a is type(None))
def _handle_none_type(annotation: Any, ctx: StubContext) -> str:
    """``NoneType`` renders as ``None``."""
    return "None"


@builtin_handler(lambda a: a is ...)
def _handle_ellipsis(annotation: Any, ctx: StubContext) -> str:
    """``...`` as in ``tuple[X, ...]``."""
    return "..."


@builtin_handler(lambda a: _UnionType is not None and isinstance(a, _UnionType))
def _handle_pep604_union(annotation: Any, ctx: StubContext) -> str:
    """PEP 604 ``X | Y`` unions, rendered per ``union_style``."""
    modern = getattr(ctx.config, "union_style", "modern") == "modern"
    args = annotation.__args__
    none_type = type(None)
    non_none_args = [a for a in args if a is not none_type]
    has_none = len(args) != len(non_none_args)

    if has_none and len(non_none_args) > 1:
        alias = _optional_alias(non_none_args, ctx, modern)
        if alias:
            return alias

    if modern:
        return " | ".join(annotation_to_str(a, ctx) for a in args)

    if has_none and len(non_none_args) == 1:
        return f"Optional[{annotation_to_str(non_none_args[0], ctx)}]"

    parts = [annotation_to_str(a, ctx) for a in args]
    return f"Union[{', '.join(parts)}]"


@builtin_handler(lambda a: isinstance(a, _TYPEVAR_LIKE_TYPES))
def _handle_typevar(annotation: Any, ctx: StubContext) -> str:
    """``TypeVar`` / ``ParamSpec`` / ``TypeVarTuple`` render as their bare name."""
    return annotation.__name__


def _render_union(annotation: Any, ctx: StubContext) -> str:
    """Render a ``typing.Union`` / ``Optional`` per ``union_style``."""
    args = annotation.__args__
    if not args:
        return "Union"
    modern = getattr(ctx.config, "union_style", "modern") == "modern"
    none_type = type(None)
    non_none = [a for a in args if a is not none_type]
    has_none = any(a is none_type for a in args)

    if has_none and len(non_none) > 1:
        alias = _optional_alias(non_none, ctx, modern)
        if alias:
            return alias

    if modern:
        parts = [annotation_to_str(a, ctx) for a in args]
        return " | ".join([p for p in parts if p != "None"] + [p for p in parts if p == "None"])

    if has_none and len(non_none) == 1:
        return f"Optional[{annotation_to_str(non_none[0], ctx)}]"
    parts = [annotation_to_str(a, ctx) for a in args]
    return f"Union[{', '.join(parts)}]"


def _render_callable(annotation: Any, ctx: StubContext) -> str:
    """Render ``Callable[[params], ret]``."""
    args = annotation.__args__
    if not args:
        return "Callable"
    *param_types, ret_type = args
    ret_str = annotation_to_str(ret_type, ctx)
    if param_types and param_types[0] is not None:
        params_str = "[" + ", ".join(annotation_to_str(p, ctx) for p in param_types) + "]"
    else:
        params_str = "[]"
    return f"Callable[{params_str}, {ret_str}]"


@builtin_handler(lambda a: (
    isinstance(a, _builtin_types.GenericAlias)
    or getattr(a, "__origin__", None) is not None
))
def _handle_generic(annotation: Any, ctx: StubContext) -> str:
    """Subscripted generics: ``Union``, ``Callable``, ``Literal`` and containers.

    Registered before the plain-type handler so subscripted builtins such
    as ``list[int]`` are not caught by ``isinstance(a, type)``.
    """
    origin = annotation.__origin__

    if origin is typing.Union:
        return _render_union(annotation, ctx)

    if origin is collections.abc.Callable:
        return _render_callable(annotation, ctx)

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
        parts = []
        for arg in args:
            try:
                parts.append(annotation_to_str(arg, ctx))
            except Exception:
                parts.append(str(arg).replace("typing.", ""))
        return f"{origin_name}[{', '.join(parts)}]"
    return origin_name


@builtin_handler(lambda a: isinstance(a, type))
def _handle_plain_type(annotation: Any, ctx: StubContext) -> str:
    """Plain classes render as ``__name__``."""
    return annotation.__name__


@builtin_handler(lambda a: getattr(a, "_name", None) is not None)
def _handle_bare_typing_alias(annotation: Any, ctx: StubContext) -> str:
    """Bare typing aliases such as ``List`` and ``Dict``."""
    return annotation._name  # type: ignore[union-attr]
