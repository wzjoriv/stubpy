"""``Attr``: a data descriptor that stores values in ``element.attributes``."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

from .values import svg_name

if TYPE_CHECKING:
    from ..elements.base import Element

__all__ = ["Attr"]

T = TypeVar("T")


class Attr(Generic[T]):
    """Expose one SVG attribute as a Python attribute.

    Parameters
    ----------
    name : str, optional
        SVG attribute name; derived from the Python name when omitted.
    convert : callable, optional
        Applied to raw strings (for instance values read by the parser).
    default : object, optional
        Returned when the attribute is not set.
    """

    __slots__ = ("convert", "default", "name", "svg")

    def __init__(
        self,
        name: str | None = None,
        *,
        convert: Callable[[Any], T] | None = None,
        default: T | None = None,
    ) -> None:
        self.svg = name
        self.name = name or ""
        self.convert = convert
        self.default = default

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        if self.svg is None:
            self.svg = svg_name(name)

    @overload
    def __get__(self, obj: None, owner: type | None = None) -> Attr[T]: ...
    @overload
    def __get__(self, obj: Element, owner: type | None = None) -> T | None: ...
    def __get__(self, obj: Element | None, owner: type | None = None) -> Attr[T] | T | None:
        if obj is None:
            return self
        raw = obj.attributes.get(self.key)
        if raw is None:
            return self.default
        if self.convert is not None and isinstance(raw, str):
            return self.convert(raw)
        return raw

    def __set__(self, obj: Element, value: T | str | None) -> None:
        obj.set(self.key, value)

    def __delete__(self, obj: Element) -> None:
        obj.attributes.pop(self.key, None)

    @property
    def key(self) -> str:
        assert self.svg is not None
        return self.svg

    def __repr__(self) -> str:
        return f"Attr({self.key!r})"
