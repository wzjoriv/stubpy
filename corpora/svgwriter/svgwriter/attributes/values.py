"""Attribute names, number formatting, references and value serialization."""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from functools import singledispatch

from .protocols import SupportsSVG

__all__ = ["DEFAULT_PRECISION", "IRI", "FuncIRI", "format_number", "format_value", "svg_name"]

DEFAULT_PRECISION = 4
_CAMEL = {"attribute_name": "attributeName", "view_box": "viewBox", "path_length": "pathLength", "std_deviation": "stdDeviation"}


def svg_name(name: str) -> str:
    """Map a Python keyword (``stroke_width``, ``class_``) to its SVG name."""
    if name in _CAMEL:
        return _CAMEL[name]
    if name.startswith("xlink_"):
        return "xlink:" + name[6:]
    return name.rstrip("_").replace("_", "-")


def format_number(value: float, precision: int = DEFAULT_PRECISION) -> str:
    """Format *value* with at most *precision* decimals and no trailing zeros."""
    if math.isinf(value) or math.isnan(value):
        raise ValueError("not a finite number")
    if float(value).is_integer():
        return str(int(value))
    text = f"{value:.{precision}f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


@dataclass(frozen=True)
class IRI:
    """A plain IRI, local (``#id``) or external."""

    target: str

    @classmethod
    def local(cls, element_id: str) -> IRI:
        return cls("#" + element_id)

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return self.target


@dataclass(frozen=True)
class FuncIRI(IRI):
    """A functional IRI, ``url(...)``, as used by paint and filter."""

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return f"url({self.target})"


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


@format_value.register(float)
def _format_float(value: float, precision: int = DEFAULT_PRECISION) -> str:
    return format_number(value, precision)


@format_value.register(enum.Enum)
def _format_enum(value: enum.Enum, precision: int = DEFAULT_PRECISION) -> str:
    return format_value(value.value, precision)


@format_value.register(tuple)
@format_value.register(list)
def _format_sequence(value: tuple[object, ...] | list[object], precision: int = DEFAULT_PRECISION) -> str:
    return " ".join(format_value(item, precision) for item in value)
