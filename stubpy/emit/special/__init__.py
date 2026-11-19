"""
Dedicated stub handling for dataclasses, NamedTuples, TypedDicts and enums.
"""
from .detect import (
    dataclass_transform_decorator,
    is_dataclass,
    is_enum,
    is_namedtuple,
    is_type_check_only,
    is_typeddict,
)

__all__ = [
    "dataclass_transform_decorator",
    "is_dataclass",
    "is_enum",
    "is_namedtuple",
    "is_type_check_only",
    "is_typeddict",
]
