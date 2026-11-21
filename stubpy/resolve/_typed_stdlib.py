"""
Typed signatures for common standard-library callees, whatever the interpreter reports for them.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import cache
from typing import Any

from stubpy.resolve._constants import STDLIB_MODULE_ALIASES, STDLIB_SIGNATURES


def table_key(dotted: str) -> str:
    """*dotted* with its module replaced by the one :data:`~stubpy._constants.STDLIB_SIGNATURES` uses."""
    module, _, name = dotted.rpartition(".")
    return f"{STDLIB_MODULE_ALIASES.get(module, module)}.{name}" if module else dotted


def object_key(obj: Any) -> str:
    """The table key of the callable *obj*, from its module and qualified name."""
    return table_key(f"{_text(obj, '__module__')}.{_text(obj, '__qualname__')}")


def _text(obj: Any, attr: str) -> str:
    """*obj*'s *attr* when it is a string, else ``""`` (some objects answer any attribute with themselves)."""
    try:
        value = getattr(obj, attr, "")
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


@cache
def _compiled(key: str) -> Any:
    namespace: dict[str, Any] = {"Callable": Callable}
    exec(STDLIB_SIGNATURES[key], namespace)
    return namespace[key.rpartition(".")[2]]


def typed_stdlib_params(key: str) -> list | None:
    """The ``(parameter, hints)`` pairs of the tabled callee *key*, or ``None`` when it is not tabled."""
    if key not in STDLIB_SIGNATURES:
        return None
    fn = _compiled(key)
    hints = dict(fn.__annotations__)
    return [(p, hints) for p in inspect.signature(fn).parameters.values()]
