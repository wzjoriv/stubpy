"""Asynchronous wrappers around the writer."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Final

from .._internal._typing import AnyPath
from ..elements.base import Element
from .writer import Writer, write

__all__ = ["aiter_chunks", "write_async"]

CHUNKS_PER_YIELD: Final = 64


async def write_async(element: Element, path: AnyPath, **kwargs: Any) -> None:
    """Write *element* to *path* in a worker thread."""
    await asyncio.to_thread(write, element, path, **kwargs)


async def aiter_chunks(element: Element, **kwargs: Any) -> AsyncIterator[str]:
    """Async generator of serialized chunks, yielding control periodically."""
    for index, chunk in enumerate(Writer(**kwargs).iter_chunks(element)):
        if index % CHUNKS_PER_YIELD == 0:
            await asyncio.sleep(0)
        yield chunk
