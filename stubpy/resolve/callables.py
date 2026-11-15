"""Callable unwrapping and run-scoped caches for signatures, type hints and sources."""
from __future__ import annotations

import ast
import builtins
import contextlib
import contextvars
import functools
import inspect
import textwrap
import typing
from collections.abc import Callable, Iterator
from typing import Any

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.analysis.harvest import FunctionInfo, harvest_function
from stubpy.compiled.detect import is_compiled_callable
from stubpy.compiled.runtime import compiled_signature

_CACHE: contextvars.ContextVar[dict[tuple[str, int], tuple[Any, Any]] | None] = contextvars.ContextVar(
    "stubpy_introspection_cache", default=None,
)


@contextlib.contextmanager
def introspection_cache() -> Iterator[None]:
    """Cache signatures, hints and parsed sources inside the block; nested blocks share the outer cache."""
    if _CACHE.get() is not None:
        yield
        return
    token = _CACHE.set({})
    try:
        yield
    finally:
        _CACHE.reset(token)


def _cached(kind: str, obj: Any, compute: Callable[[], Any]) -> Any:
    """Return ``compute()`` memoised on ``(kind, obj)`` while a cache is active."""
    cache = _CACHE.get()
    if cache is None:
        return compute()
    key = (kind, id(obj))
    hit = cache.get(key)
    if hit is not None and hit[0] is obj:
        return hit[1]
    value = compute()
    cache[key] = (obj, value)
    return value


def _attr(obj: Any, name: str) -> Any:
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def unwrap_callable(obj: Any) -> Any:
    """Return the function behind descriptors, decorators and JIT wrappers.

    Follows ``staticmethod`` / ``classmethod`` ``__func__``, numba
    dispatchers' ``py_func`` and ``__wrapped__`` chains (``functools.wraps``,
    ``lru_cache``), stopping on cycles.  Classes and ``functools.partial``
    objects are returned as they are.

    Examples
    --------
    >>> import functools
    >>> def f(x): ...
    >>> unwrap_callable(functools.lru_cache(f)) is f
    True
    """
    seen: set[int] = set()
    while id(obj) not in seen:
        seen.add(id(obj))
        if isinstance(obj, (type, functools.partial)):
            return obj
        if isinstance(obj, (classmethod, staticmethod)):
            obj = obj.__func__
            continue
        if not inspect.isfunction(obj) and not inspect.ismethod(obj):
            py_func = _attr(obj, "py_func")
            if py_func is not None and callable(py_func):
                obj = py_func
                continue
        wrapped = _attr(obj, "__wrapped__")
        if wrapped is not None and callable(wrapped):
            obj = wrapped
            continue
        break
    return obj


def _compute_signature(obj: Any) -> inspect.Signature | None:
    if inspect.ismethod(obj):
        sig = signature_of(obj.__func__)
        if sig is None or not sig.parameters:
            return sig
        return sig.replace(parameters=list(sig.parameters.values())[1:])
    target = unwrap_callable(obj)
    try:
        if isinstance(target, functools.partial):
            inner = unwrap_callable(target.func)
            target = functools.partial(inner, *target.args, **target.keywords)
        sig = inspect.signature(target, follow_wrapped=False)
    except (ValueError, TypeError, RecursionError):
        sig = None
    if is_compiled_callable(target) and (sig is None or _is_generic(sig)):
        return compiled_signature(target) or sig
    return sig


def _is_generic(sig: inspect.Signature) -> bool:
    """True for ``(*args, **kwargs)``, with or without a receiver in front."""
    kinds = [p.kind for p in sig.parameters.values()]
    return kinds[-2:] == [VAR_POS, VAR_KW] and len(kinds) <= 3


def signature_of(obj: Any) -> inspect.Signature | None:
    """Return the signature of the unwrapped *obj*, or ``None`` when it has none.

    Bound arguments of ``functools.partial`` objects are removed and a bound
    method loses its first parameter.
    """
    return _cached("signature", obj, lambda: _compute_signature(obj))


class OwnedHints(dict):
    """Resolved type hints that remember the function they belong to (``owner``), for source lookups."""

    owner: Any = None


def _owned(hints: dict[str, Any], owner: Any) -> OwnedHints:
    result = OwnedHints(hints)
    result.owner = owner
    return result


def _compute_hints(fn: Any) -> OwnedHints:
    raw = unwrap_callable(fn.fget if isinstance(fn, property) else fn)
    if isinstance(raw, functools.partial):
        raw = unwrap_callable(raw.func)
    try:
        return _owned(typing.get_type_hints(raw), raw)
    except Exception:
        pass
    try:
        localns = vars(builtins).copy()
        localns.update(_attr(raw, "__globals__") or {})
        return _owned(typing.get_type_hints(raw, localns=localns), raw)
    except Exception:
        pass
    annotations = _attr(raw, "__annotations__")
    return _owned(dict(annotations) if isinstance(annotations, dict) else {}, raw)


def hints_of(fn: Any) -> dict[str, Any]:
    """Return resolved type hints of the unwrapped *fn*; raw ``__annotations__`` when they do not resolve."""
    if fn is None:
        return OwnedHints()
    return _cached("hints", fn, lambda: _compute_hints(fn))


def _compute_class_hints(cls: type) -> dict[str, Any] | None:
    try:
        return typing.get_type_hints(cls)
    except Exception:
        return None


def class_hints_of(cls: type) -> dict[str, Any] | None:
    """Return ``typing.get_type_hints(cls)``, or ``None`` when the hints do not resolve."""
    return _cached("class_hints", cls, lambda: _compute_class_hints(cls))


def _compute_source_tree(fn: Any) -> ast.Module | None:
    try:
        return ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except Exception:
        return None


def source_tree_of(fn: Any) -> ast.Module | None:
    """Return the parsed source of *fn*, or ``None`` when it is unavailable."""
    return _cached("source", fn, lambda: _compute_source_tree(fn))


def _compute_function_info(fn: Any) -> FunctionInfo | None:
    target = unwrap_callable(fn.fget if isinstance(fn, property) else fn)
    if isinstance(target, functools.partial) or isinstance(target, type):
        return None
    tree = source_tree_of(target)
    if tree is None:
        return None
    node = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
    return harvest_function(node) if node is not None else None


def function_info_of(fn: Any) -> FunctionInfo | None:
    """Return the AST :class:`FunctionInfo` of the unwrapped *fn*, harvested from its source; ``None`` without source."""
    if fn is None:
        return None
    return _cached("function_info", fn, lambda: _compute_function_info(fn))
