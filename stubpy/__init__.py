"""Generate ``.pyi`` stub files, with ``**kwargs`` / ``*args`` traced back to the parameters they forward to.

Usage::

    import stubpy

    stubpy.generate("src/mypkg", "stubs")              # write stubs; returns a Report
    print(stubpy.render("mod.py").text)                # one module, nothing written
    report = stubpy.check("src/mypkg", "stubs")        # stale stubs, for CI
    stubpy.generate("mypkg.core", config=stubpy.Config(mode="ast", include_private=True))
    stubpy.generate(config=stubpy.load_config())       # targets from [tool.stubpy]

    from stubpy import hint

    @hint.signature("(x: float) -> float")             # what introspection cannot see
    def jitted(x): ...

From the shell: ``stubpy src/mypkg -o stubs``, ``stubpy check --diff``, ``stubpy render mod.py``.

Sub-packages
------------
config
    :class:`Config`, :class:`Mode`, the style enums and config-file loading.
core
    Run context, diagnostics, results, target resolution and ``render`` / ``generate`` / ``check``.
analysis
    Module loading, the AST pre-pass, import scanning, aliases, hints, the
    symbol table and docstring type inference.
resolve
    ``**kwargs`` / ``*args`` back-tracing through the MRO and forwarding calls.
emit
    Stub text for classes, functions, variables, aliases and overloads.
cli
    The ``stubpy`` command.
"""
from . import extend, hint
from .config import Config, Mode, load_config
from .core import Diagnostic, Level, Report, StubResult
from .core.api import check, generate, render

__version__ = "0.7.0"
__author__ = "Josue N Rivera"

__all__ = [
    "render",
    "generate",
    "check",
    "Config",
    "Mode",
    "load_config",
    "StubResult",
    "Report",
    "Diagnostic",
    "Level",
    "hint",
    "extend",
    "__version__",
]
