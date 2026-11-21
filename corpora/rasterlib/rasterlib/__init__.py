"""rasterlib: compiled raster primitives in every common binding style, kept as a stubpy test corpus."""
from __future__ import annotations

import importlib

__version__ = "0.3.0"

NATIVE_MODULES = {
    "_scanline": "CPython C API",
    "_geometry": "CPython C API (no signature docstrings)",
    "_codec": "Cython (embedsignature)",
    "_pattern": "Cython",
    "_filters": "pybind11",
    "_composite": "nanobind",
}


def backend_info() -> dict[str, bool]:
    """Which compiled modules import on this interpreter."""
    found = {}
    for name in NATIVE_MODULES:
        try:
            importlib.import_module(f"{__name__}.{name}")
            found[name] = True
        except ImportError:
            found[name] = False
    return found
