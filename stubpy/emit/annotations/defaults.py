"""Rendering of parameter default values."""
from __future__ import annotations

import enum
import inspect
from typing import Any


class NonLiteralDefault:
    """A non-literal default from AST-only mode, rendered as its source expression."""
    __slots__ = ("_repr",)

    def __init__(self, source_repr: str) -> None:
        self._repr = source_repr

    def __repr__(self) -> str:
        return self._repr


def default_to_str(default: Any) -> str:
    """Render a parameter default as stub text; ``""`` for ``inspect.Parameter.empty``.

    Enum members render as ``Class.MEMBER`` and classes by name.

    Examples
    --------
    >>> default_to_str("black")
    "'black'"
    >>> default_to_str(None)
    'None'
    """
    if default is inspect.Parameter.empty:
        return ""
    if isinstance(default, enum.Enum):
        return f"{type(default).__name__}.{default.name}"
    if isinstance(default, type):
        return default.__name__
    if hasattr(default, "__slots__") and hasattr(default, "_repr"):
        return str(default)
    return repr(default)
