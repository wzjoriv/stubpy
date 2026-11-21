"""Generate ``.pyi`` stub files, with ``**kwargs`` / ``*args`` traced back to the parameters they forward to.

Usage::

    import stubpy

    stubpy.generate("src/mypkg", "stubs")              # write stubs; returns a Report
    print(stubpy.render("mod.py").text)                # one module, nothing written
    report = stubpy.check("src/mypkg", "stubs")        # stale stubs, for CI
    stubpy.generate("mypkg.core", config=stubpy.Config(imports="none", include_private=True))
    stubpy.generate("mypkg._native", output="stubs")   # compiled extension (.pyd / .so) by name
    stubpy.generate(config=stubpy.load_config())       # targets from [tool.stubpy]
    stubpy.sync_docstrings("mypkg/_native.pyi")        # runtime docstrings into a hand-written stub

    from stubpy import hint

    @hint.signature("(x: float) -> float")             # what introspection cannot see
    def jitted(x): ...

From the shell: ``stubpy src/mypkg -o stubs``, ``stubpy check --diff``, ``stubpy render mod.py``,
``stubpy docstrings sync mypkg/_native.pyi``.

The public names are imported on first use (module ``__getattr__``), so
``from stubpy import hint`` stays cheap for projects that only use the hints.

Sub-packages
------------
config
    :class:`Config`, the style enums and config-file loading.
core
    Run context, diagnostics, results, target resolution and ``render`` / ``generate`` / ``check``.
analysis
    Module loading, the AST pre-pass, import scanning, aliases, hints, the
    symbol table and docstring type inference.
resolve
    ``**kwargs`` / ``*args`` back-tracing through the MRO and forwarding calls.
compiled
    Extension modules (C API, Cython, pybind11, nanobind): signatures,
    introspection into a symbol table, and docstring sync.
emit
    Stub text for classes, functions, variables, aliases and overloads.
cli
    The ``stubpy`` command.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import extend, hint
    from .compiled.docsync import sync_docstrings
    from .config import Config, load_config
    from .core import Report, StubResult
    from .core.api import check, generate, render
    from .state import Diagnostic, Level

__version__ = "0.11.3"
__author__ = "Josue N Rivera"

__all__ = [
    "render",
    "generate",
    "check",
    "Config",
    "load_config",
    "sync_docstrings",
    "StubResult",
    "Report",
    "Diagnostic",
    "Level",
    "hint",
    "extend",
    "__version__",
]

_LAZY: dict[str, tuple[str, str | None]] = {
    "render": (".core.api", "render"),
    "generate": (".core.api", "generate"),
    "check": (".core.api", "check"),
    "Config": (".config", "Config"),
    "load_config": (".config", "load_config"),
    "sync_docstrings": (".compiled.docsync", "sync_docstrings"),
    "StubResult": (".core", "StubResult"),
    "Report": (".core", "Report"),
    "Diagnostic": (".state", "Diagnostic"),
    "Level": (".state", "Level"),
    "hint": (".hint", None),
    "extend": (".extend", None),
}


def __getattr__(name: str) -> Any:
    """Import a public name on first access and cache it in the module namespace."""
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0], __name__)
    value = module if target[1] is None else getattr(module, target[1])
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
