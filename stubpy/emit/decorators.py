"""Decorators that carry meaning in a stub; all others are dropped."""
from __future__ import annotations

import ast

from stubpy._constants import PROPERTY_ACCESSOR_DECORATORS, STUB_DECORATORS

_KEEP_ARGUMENTS: frozenset[str] = frozenset({"deprecated", "dataclass", "dataclass_transform"})


def _parse(text: str) -> ast.expr | None:
    try:
        return ast.parse(text.strip().lstrip("@"), mode="eval").body
    except SyntaxError:
        return None


def decorator_base_name(text: str) -> str:
    """Return the last dotted component of the decorator's callee: ``functools.cache(...)`` gives ``cache``.

    Examples
    --------
    >>> decorator_base_name("functools.lru_cache(maxsize=None)")
    'lru_cache'
    """
    node = _parse(text)
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def stub_decorator(text: str) -> str | None:
    """Return the stub form of one source decorator, or ``None`` when a stub should drop it.

    Module prefixes are removed (``abc.abstractmethod`` gives ``abstractmethod``);
    property accessors keep their owner (``x.setter``); ``deprecated``,
    ``dataclass`` and ``dataclass_transform`` keep their arguments.

    Examples
    --------
    >>> stub_decorator("functools.cached_property")
    'cached_property'
    >>> stub_decorator("app.route('/')") is None
    True
    >>> stub_decorator("value.setter")
    'value.setter'
    """
    node = _parse(text)
    call = node if isinstance(node, ast.Call) else None
    func = call.func if call is not None else node
    if (
        call is None
        and isinstance(func, ast.Attribute)
        and func.attr in PROPERTY_ACCESSOR_DECORATORS
        and isinstance(func.value, ast.Name)
    ):
        return f"{func.value.id}.{func.attr}"
    if isinstance(func, ast.Attribute):
        base = func.attr
    elif isinstance(func, ast.Name):
        base = func.id
    else:
        return None
    if base not in STUB_DECORATORS:
        return None
    if call is not None and base in _KEEP_ARGUMENTS:
        return ast.unparse(ast.Call(func=ast.Name(id=base), args=call.args, keywords=call.keywords))
    return base


def stub_decorators(texts: list[str]) -> list[str]:
    """Filter and normalise source decorators with :func:`stub_decorator`, keeping order."""
    return [d for d in (stub_decorator(t) for t in texts) if d is not None]
