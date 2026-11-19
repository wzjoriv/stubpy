"""
Detection of class kinds that need dedicated stub handling.
"""
from __future__ import annotations

import enum
from typing import Any

from stubpy.core.context import StubContext
from stubpy.emit.annotations.defaults import ELLIPSIS, render_default


def is_dataclass(cls: type) -> bool:
    """Return ``True`` when *cls* was decorated with ``@dataclass``."""
    return hasattr(cls, "__dataclass_fields__")


def is_namedtuple(cls: type) -> bool:
    """Return ``True`` when *cls* is a NamedTuple subclass."""
    return (
        isinstance(cls, type)
        and issubclass(cls, tuple)
        and hasattr(cls, "_fields")
        and hasattr(cls, "_asdict")
    )


def is_typeddict(cls: type) -> bool:
    """Return ``True`` when *cls* was created via ``TypedDict``."""
    return (
        isinstance(cls, type)
        and hasattr(cls, "__total__")
        and hasattr(cls, "__required_keys__")
        and hasattr(cls, "__optional_keys__")
    )


def is_enum(cls: type) -> bool:
    """Return ``True`` when *cls* is an :class:`~enum.Enum` subclass."""
    return isinstance(cls, type) and issubclass(cls, enum.Enum)


def is_type_check_only(cls: type) -> bool:
    """Return ``True`` when *cls* is decorated with ``@typing.type_check_only``."""
    return bool(getattr(cls, "__type_check_only__", False))


def _transform_value(value: Any, ctx: StubContext | None) -> str | None:
    """Render one ``dataclass_transform`` argument; field specifiers become a tuple of names."""
    if isinstance(value, tuple):
        parts = [render_default(v, ctx) for v in value]
        if any(p == ELLIPSIS for p in parts):
            return None
        return "(" + ", ".join(parts) + ("," if len(parts) == 1 else "") + ")"
    text = render_default(value, ctx)
    return None if text == ELLIPSIS else text


def dataclass_transform_decorator(cls: type, ctx: StubContext | None = None) -> str | None:
    """Return the ``@dataclass_transform(...)`` line for a PEP 681 transform class, else ``None``.

    Arguments that cannot be written as names in scope are left out.
    """
    params = getattr(cls, "__dataclass_transform__", None)
    if not isinstance(params, dict):
        return None
    items = []
    for k, v in params.items():
        if k not in ("eq_default", "order_default", "frozen_default", "field_specifiers", "kw_only_default"):
            continue
        text = _transform_value(v, ctx)
        if text is not None:
            items.append(f"{k}={text}")
    return f"@dataclass_transform({', '.join(items)})"
