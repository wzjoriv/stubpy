"""
devkit: project-agnostic developer tools behind one typer app, configured by [tool.devkit].
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

import typer

from . import deps
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
    "stub": "stub",
    "tiers": "tiers",
    "bench": "bench",
    "version": "version",
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


class _App(typer.Typer):
    """A typer app that reports a bad ``[tool.devkit]`` setting or hook as a message (exit 2), not a traceback."""

    error: ConfigError | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        try:
            if self.error is not None:
                raise self.error
            return super().__call__(*args, **kwargs)
        except ConfigError as exc:
            typer.echo(f"devkit: {exc}", err=True)
            raise SystemExit(2) from None


def _populate(app: _App) -> None:
    if section("pyi") is not None:
        raise ConfigError("[tool.devkit.pyi] was renamed [tool.devkit.stub] (the tool now runs stubpy)")
    deps.register(app)
    for key, module in GENERAL.items():
        cfg = section(key)
        if cfg is not None:
            importlib.import_module(f"{__name__}.{module}").register(app, cfg)
    for spec in typed(settings(), "tools", list, [], "tool.devkit"):
        _project_tool(app, spec)


def make_app() -> typer.Typer:
    """The developer app: the enabled general tools and the project's own tools."""
    _never_fail_on_encoding()
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))  # project tools import by their folder name
    app = _App(
        help=f"Developer tools of {project_name()}.",
        no_args_is_help=True,
        add_completion=False,
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    try:
        _populate(app)
    except ConfigError as exc:
        app.error = exc
    return app
