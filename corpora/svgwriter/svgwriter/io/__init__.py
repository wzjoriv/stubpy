"""Writing SVG text, files and streams; the async helpers load on first attribute access."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from .writer import SerializeOptions, Writer, iter_chunks, to_string, write

if TYPE_CHECKING:
    from ._async import aiter_chunks, write_async

_LAZY = {"aiter_chunks": "._async", "write_async": "._async"}

__all__ = ["SerializeOptions", "Writer", "aiter_chunks", "iter_chunks", "to_string", "write", "write_async"]


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        value = getattr(importlib.import_module(_LAZY[name], __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
