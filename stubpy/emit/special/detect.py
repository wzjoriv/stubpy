"""Detection of class kinds that need dedicated stub handling."""
from __future__ import annotations

import enum


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


def dataclass_transform_decorator(cls: type) -> str | None:
    """Return the ``@dataclass_transform(...)`` line for a PEP 681 transform class, else ``None``."""
    if not hasattr(cls, "__dataclass_transform__"):
        return None
    items = [
        f"{k}={v!r}"
        for k, v in cls.__dataclass_transform__.items()
        if k in ("eq_default", "order_default", "frozen_default", "field_specifiers", "kw_only_default")
    ]
    return f"@dataclass_transform({', '.join(items)})"
