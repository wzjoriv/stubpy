"""Discovery of the optional native layers and the pure-Python switch."""
from __future__ import annotations

import contextlib
import importlib
import os
import threading
from collections.abc import Iterator
from types import ModuleType

PURE_ENV = "SVGRASTER_PURE"
NATIVE_MODULES = {
    "scanline": ("svgraster._scanline", "CPython C API"),
    "glyf": ("svgraster._glyf", "CPython C API"),
    "paint": ("svgraster._paint", "Cython (embedsignature, binding)"),
    "pattern": ("svgraster._pattern", "Cython"),
    "codec": ("svgraster._codec", "Cython (embedsignature, cpdef enums)"),
    "filters": ("svgraster._filters", "pybind11"),
    "composite": ("svgraster._composite", "nanobind"),
    "bidi": ("svgraster._bidi", "Cython (typed memoryviews, nogil)"),
}

_modules: dict[str, ModuleType | None] = {}
_errors: dict[str, str] = {}
_state = threading.local()


def _import(layer: str) -> ModuleType | None:
    if os.environ.get(PURE_ENV, "") not in ("", "0"):
        _errors[layer] = f"disabled by {PURE_ENV}"
        return None
    name = NATIVE_MODULES[layer][0]
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        _errors[layer] = str(exc)
        return None


def module(layer: str) -> ModuleType | None:
    """The compiled module for ``layer`` if built and not disabled."""
    if layer not in _modules:
        _modules[layer] = _import(layer)
    return _modules[layer]


def native(layer: str) -> ModuleType | None:
    """Like :func:`module` but honours :func:`pure_python` for this thread."""
    if getattr(_state, "pure", False):
        return None
    return module(layer)


@contextlib.contextmanager
def pure_python(enabled: bool = True) -> Iterator[None]:
    """Force the numpy fallbacks inside the ``with`` block (per thread)."""
    previous = getattr(_state, "pure", False)
    _state.pure = enabled
    try:
        yield
    finally:
        _state.pure = previous


def backend_info() -> dict[str, dict[str, object]]:
    """Which native layers are importable, their technology and OpenMP use."""
    from . import _jit

    info: dict[str, dict[str, object]] = {}
    for layer, (name, tech) in NATIVE_MODULES.items():
        mod = module(layer)
        info[layer] = {
            "module": name,
            "technology": tech,
            "available": mod is not None,
            "openmp": bool(getattr(mod, "HAVE_OPENMP", False)) if mod is not None else False,
            "error": None if mod is not None else _errors.get(layer),
        }
    info["jit"] = {
        "module": "svgraster._jit",
        "technology": "numba",
        "available": _jit.HAVE_NUMBA,
        "openmp": False,
        "error": None if _jit.HAVE_NUMBA else _jit.NUMBA_ERROR,
    }
    return info
