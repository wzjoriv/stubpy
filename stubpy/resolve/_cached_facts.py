"""
Cached per-object facts: owned type hints, class hints, source trees and harvested function info.
"""
from __future__ import annotations

import ast
import builtins
import functools
import inspect
import textwrap
import typing
from typing import Any

from stubpy.analysis.harvest import FunctionInfo, harvest_function

from .callables import _attr, _cached, unwrap_callable


class OwnedHints(dict):
    """Resolved type hints that remember the function they belong to (``owner``), for source lookups.

    A ``dict`` of parameter names to hints, with the extra attributes ``owner``
    (``None`` until set) and ``source_names`` (a parameter key here to its key in
    the owner's source, for a parameter renamed while merging).

    Examples
    --------
    >>> hints = OwnedHints(x=int)
    >>> hints["x"], hints.owner
    (<class 'int'>, None)
    """

    owner: Any = None
    source_names: dict[str, str] = {}


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
    """Return resolved type hints of the unwrapped *fn*; raw ``__annotations__`` when they do not resolve.

    Parameters
    ----------
    fn : callable or None
        A function, method, property or wrapper; ``None`` gives empty hints.

    Returns
    -------
    dict of str to object
        Parameter names (and ``"return"``) to annotations.

    Examples
    --------
    >>> def f(x: int) -> str: ...
    >>> hints_of(f)
    {'x': <class 'int'>, 'return': <class 'str'>}
    """
    if fn is None:
        return OwnedHints()
    return _cached("hints", fn, lambda: _compute_hints(fn))


def _compute_class_hints(cls: type) -> dict[str, Any] | None:
    try:
        return typing.get_type_hints(cls)
    except Exception:
        return None


def class_hints_of(cls: type) -> dict[str, Any] | None:
    """Return ``typing.get_type_hints(cls)``, or ``None`` when the hints do not resolve.

    Parameters
    ----------
    cls : type
        The class to inspect.

    Returns
    -------
    dict of str to object or None
        Attribute names to resolved annotations, or ``None`` on failure.

    Examples
    --------
    >>> class Point:
    ...     x: int
    >>> class_hints_of(Point)
    {'x': <class 'int'>}
    """
    return _cached("class_hints", cls, lambda: _compute_class_hints(cls))


def _compute_source_tree(fn: Any) -> ast.Module | None:
    try:
        return ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except Exception:
        return None


def source_tree_of(fn: Any) -> ast.Module | None:
    """Return the parsed source of *fn*, or ``None`` when it is unavailable.

    Parameters
    ----------
    fn : callable
        A function or method.

    Returns
    -------
    ast.Module or None
        The dedented source parsed as a module, or ``None`` when there is no source.

    Examples
    --------
    >>> type(source_tree_of(hints_of)).__name__
    'Module'
    >>> source_tree_of(len) is None
    True
    """
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
    """Return the AST :class:`FunctionInfo` of the unwrapped *fn*, harvested from its source; ``None`` without source.

    Parameters
    ----------
    fn : callable or None
        A function, method or property.

    Returns
    -------
    FunctionInfo or None
        The harvested metadata, or ``None`` for classes, partials and objects without source.

    Examples
    --------
    >>> function_info_of(hints_of).name
    'hints_of'
    """
    if fn is None:
        return None
    return _cached("function_info", fn, lambda: _compute_function_info(fn))
