"""devkit: project-agnostic developer tools behind one typer app, configured by ``[tool.devkit]``.

Copy ``scripts/devkit`` as is between projects; ``scripts/dev.py`` is::

    from devkit import make_app

    app = make_app()

    if __name__ == "__main__":
        app()

``make_app`` offers each general tool in ``GENERAL`` whose ``[tool.devkit.<key>]`` table exists, then the
project's own tools listed in ``[tool.devkit] tools`` (``"module:attribute"``, importable from ``scripts/``):
a ``typer.Typer`` becomes a command group (named by its ``name=``, else by the module's top-level package), a
function becomes a command (its name, ``_`` as ``-``).
"""

from __future__ import annotations

import importlib
import sys

import typer

from .config import ConfigError, project_name, section, settings, typed
from .paths import SCRIPTS

__all__ = ["GENERAL", "make_app"]

#: The general tools: ``[tool.devkit.<key>]`` table -> module of this package. Each module has
#: ``register(app, cfg)``, adding its commands to ``app`` from its table ``cfg``.
GENERAL: dict[str, str] = {
    "check": "check",
    "docs": "docs",
    "build": "build",
    "licenses": "licenses",
    "diagrams": "diagrams",
    "pyi": "pyi",
    "tiers": "tiers",
    "bench": "bench",
}


def _project_tool(app: typer.Typer, spec: str) -> None:
    """Add the project tool ``spec`` (``"module:attribute"``) to ``app``."""
    module_name, sep, attr = spec.partition(":")
    if not sep or not module_name or not attr:
        raise ConfigError(f"[tool.devkit] tools: {spec!r} is not 'module:attribute'")
    try:
        obj = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise ConfigError(f"[tool.devkit] tools: cannot load {spec!r} from {SCRIPTS}: {exc}") from exc
    if isinstance(obj, typer.Typer):
        app.add_typer(obj, name=obj.info.name or module_name.split(".")[0].replace("_", "-"))
    elif callable(obj):
        app.command(attr.replace("_", "-"))(obj)
    else:
        raise ConfigError(f"[tool.devkit] tools: {spec!r} is neither a typer.Typer nor a function")


def _never_fail_on_encoding() -> None:
    """A code-page console or a redirected stream (Windows: cp1252) shows "?" for a character it cannot encode
    (a tool's "──" heading, a test's output) instead of raising after the work is done."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def make_app() -> typer.Typer:
    """The developer app: the enabled general tools and the project's own tools."""
    _never_fail_on_encoding()
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))  # project tools import by their folder name
    app = typer.Typer(
        help=f"Developer tools of {project_name()}.",
        no_args_is_help=True,
        add_completion=False,
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    for key, module in GENERAL.items():
        cfg = section(key)
        if cfg is not None:
            importlib.import_module(f"{__name__}.{module}").register(app, cfg)
    for spec in typed(settings(), "tools", list, [], "tool.devkit"):
        _project_tool(app, spec)
    return app
