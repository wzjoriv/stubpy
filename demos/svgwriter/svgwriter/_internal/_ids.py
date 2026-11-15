"""Automatic element id generation."""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Iterator

from ._typing import ElementId

__all__ = ["IdFactory", "next_id"]


class IdFactory:
    """Hand out ``prefix-N`` ids, counting per prefix."""

    __slots__ = ("_counters",)

    def __init__(self) -> None:
        self._counters: defaultdict[str, Iterator[int]] = defaultdict(
            lambda: itertools.count(1)
        )

    def __call__(self, prefix: str) -> ElementId:
        return ElementId(f"{prefix}{next(self._counters[prefix])}")

    def reset(self) -> None:
        self._counters.clear()


next_id = IdFactory()
