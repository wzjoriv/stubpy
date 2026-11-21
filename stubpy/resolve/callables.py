"""
Callable unwrapping and run-scoped caches for signatures, type hints and sources.
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import inspect
import sys
import typing
from collections.abc import Callable, Iterator
from typing import Any

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.compiled.detect import is_compiled_callable
from stubpy.compiled.runtime import compiled_signature

_CACHE: contextvars.ContextVar[dict[tuple[str, int], tuple[Any, Any]] | None] = contextvars.ContextVar(
    "stubpy_introspection_cache", default=None,
)


@contextlib.contextmanager
def introspection_cache() -> Iterator[None]:
    """Cache signatures, hints and parsed sources inside the block; nested blocks share the outer cache.

    Yields
    ------
    None
        Nothing; the cache is active for the duration of the ``with`` block.

    See Also
    --------
    signature_of, hints_of : Lookups that use the cache.

    Examples
    --------
    >>> with introspection_cache():
    ...     signature_of(len) is signature_of(len)
    True
    """
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
    dispatchers' ``py_func``, ``__wrapped__`` chains (``functools.wraps``,
    ``lru_cache``) and ``(*args: P.args, **kwargs: P.kwargs)`` closures
    around one function, stopping on cycles.  Classes and ``functools.partial``
    objects are returned as they are.

    Parameters
    ----------
    obj : object
        A function, descriptor or wrapper.

    Returns
    -------
    object
        The innermost function reached, or *obj* when there is nothing to unwrap.

    See Also
    --------
    signature_of : Signature of the unwrapped callable.

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
        wrapped = _paramspec_target(obj)
        if wrapped is not None:
            obj = wrapped
            continue
        break
    return obj


def _paramspec_target(fn: Any) -> Any:
    """Return the one function a ``(*args: P.args, **kwargs: P.kwargs)`` closure wraps, else ``None``."""
    annotations = _attr(fn, "__annotations__") if inspect.isfunction(fn) else None
    code = _attr(fn, "__code__")
    if not isinstance(annotations, dict) or code is None or not code.co_flags & inspect.CO_VARARGS:
        return None
    varargs = code.co_varnames[code.co_argcount + code.co_kwonlyargcount]
    annotation = annotations.get(varargs)
    if not (isinstance(annotation, typing.ParamSpecArgs) or str(annotation).endswith(".args")):
        return None
    cells = [c.cell_contents for c in (fn.__closure__ or ()) if _filled(c)]
    found = [c for c in cells if inspect.isfunction(c) or inspect.ismethod(c)]
    return found[0] if len(found) == 1 else None


def _filled(cell: Any) -> bool:
    try:
        return cell.cell_contents is not cell
    except ValueError:
        return False


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
        sig = _inspect_signature(target)
    except (ValueError, TypeError, RecursionError):
        sig = None
    if is_compiled_callable(target) and (sig is None or _is_generic(sig)):
        return compiled_signature(target) or sig
    return sig


def _inspect_signature(target: Any) -> inspect.Signature:
    """``inspect.signature`` that survives annotations naming something undefined (lazy on Python 3.14+)."""
    try:
        return inspect.signature(target, follow_wrapped=False)
    except (NameError, AttributeError):
        if sys.version_info < (3, 14):
            raise TypeError("annotations do not evaluate") from None
        import annotationlib
        return inspect.signature(target, follow_wrapped=False, annotation_format=annotationlib.Format.FORWARDREF)


def _is_generic(sig: inspect.Signature) -> bool:
    """True for ``(*args, **kwargs)``, with or without a receiver in front."""
    kinds = [p.kind for p in sig.parameters.values()]
    return kinds[-2:] == [VAR_POS, VAR_KW] and len(kinds) <= 3


def signature_of(obj: Any) -> inspect.Signature | None:
    """Return the signature of the unwrapped *obj*, or ``None`` when it has none.

    Bound arguments of ``functools.partial`` objects are removed and a bound
    method loses its first parameter.

    Parameters
    ----------
    obj : object
        A callable, possibly wrapped.

    Returns
    -------
    inspect.Signature or None
        The signature, or ``None`` when it cannot be determined.

    Examples
    --------
    >>> str(signature_of(lambda a, b=1: None))
    '(a, b=1)'
    """
    return _cached("signature", obj, lambda: _compute_signature(obj))
