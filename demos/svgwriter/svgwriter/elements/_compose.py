"""``Composable``: ``a + b`` builds a group."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Element
    from .structure import Group

__all__ = ["Composable"]


class Composable:
    """Mixin giving every element ``+`` and reflected ``+``.

    The operands are moved into the new group, not copied.
    """

    __slots__ = ()

    def __add__(self: Element, other: Element | Iterable[Element]) -> Group:
        """``a + b``: a new ``<g>`` holding both (moved, not copied)."""
        from .container import flatten
        from .structure import Group

        try:
            items = flatten(other)
        except TypeError:
            return NotImplemented
        return Group(self, *items)

    def __radd__(self: Element, other: Iterable[Element]) -> Group:
        """``[a, b] + c``: a new ``<g>`` holding all three."""
        from .container import flatten
        from .structure import Group

        try:
            items = flatten(other)
        except TypeError:
            return NotImplemented
        return Group(*items, self)
