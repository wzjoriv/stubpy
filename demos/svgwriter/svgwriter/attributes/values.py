"""Attribute value serialization via ``functools.singledispatch``."""

from __future__ import annotations

import enum
from collections.abc import Mapping
from functools import singledispatch

from .._internal._constants import DEFAULT_PRECISION
from .._internal._speedups import format_number
from .protocols import SupportsSVG

__all__ = ["format_value"]


@singledispatch
def format_value(value: object, precision: int = DEFAULT_PRECISION) -> str:
    """Render *value* as the text of an SVG attribute."""
    if isinstance(value, SupportsSVG):
        return value.svg_value(precision)
    return str(value)


@format_value.register(str)
def _format_str(value: str, precision: int = DEFAULT_PRECISION) -> str:
    return value


@format_value.register(bool)
def _format_bool(value: bool, precision: int = DEFAULT_PRECISION) -> str:
    return "true" if value else "false"


@format_value.register(int)
def _format_int(value: int, precision: int = DEFAULT_PRECISION) -> str:
    return str(value)


@format_value.register(float)
def _format_float(value: float, precision: int = DEFAULT_PRECISION) -> str:
    return format_number(value, precision)


@format_value.register(enum.Enum)
def _format_enum(value: enum.Enum, precision: int = DEFAULT_PRECISION) -> str:
    if isinstance(value, SupportsSVG):
        return value.svg_value(precision)
    return format_value(value.value, precision)


@format_value.register(tuple)
@format_value.register(list)
def _format_sequence(value: tuple[object, ...] | list[object], precision: int = DEFAULT_PRECISION) -> str:
    parts = []
    for item in value:
        if isinstance(item, (tuple, list)):
            parts.append(",".join(format_value(part, precision) for part in item))
        else:
            parts.append(format_value(item, precision))
    return " ".join(parts)


@format_value.register(Mapping)
def _format_mapping(value: Mapping[str, object], precision: int = DEFAULT_PRECISION) -> str:
    from .style import Style

    return Style(value).svg_value(precision)
