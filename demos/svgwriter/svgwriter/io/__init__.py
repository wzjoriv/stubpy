"""Reading and writing SVG text, files and streams.

The writer is imported eagerly; the parser and async helpers load on first
attribute access.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from .writer import SerializeOptions, Writer, iter_chunks, to_string, write

if TYPE_CHECKING:
    from ._async import aiter_chunks, write_async, write_many_async
    from .parser import SVGParseError, Strictness, parse, parse_file

_LAZY = {
    "SVGParseError": ".parser",
    "Strictness": ".parser",
    "parse": ".parser",
    "parse_file": ".parser",
    "aiter_chunks": "._async",
    "write_async": "._async",
    "write_many_async": "._async",
}

__all__ = [
    "SVGParseError",
    "SerializeOptions",
    "Strictness",
    "Writer",
    "aiter_chunks",
    "iter_chunks",
    "parse",
    "parse_file",
    "to_string",
    "write",
    "write_async",
    "write_many_async",
]


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        value = getattr(importlib.import_module(_LAZY[name], __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
