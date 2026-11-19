"""
Run lint, tests, the docs build and the project's own checks one after another; non-zero when one fails.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import typer

from .config import root_path, typed
from .hooks import hooks
from .paths import ROOT

__all__ = ["register"]

WHERE = "tool.devkit.check"
REQUIRES: tuple[str, ...] = ("ruff>=0.6", "pytest>=7.0")
EXTERNAL: tuple[str, ...] = ()


def requires(cfg: dict[str, Any]) -> tuple[str, ...]:
    """Sphinx too, when the ``docs`` key is set."""
    return ("sphinx",) if cfg.get("docs") else ()


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``check`` command, configured by ``[tool.devkit.check]`` (``cfg``)."""
    lint = typed(cfg, "lint", list, [], WHERE)
    tests = typed(cfg, "tests", list, None, WHERE)
    docs = typed(cfg, "docs", str, "", WHERE)
    docs_out = typed(cfg, "docs_out", str, "docs/_build/html", WHERE)
    extra = typed(cfg, "hooks", list, [], WHERE)

    def check(docs_too: bool = typer.Option(True, "--docs/--no-docs", help="Also build the docs (warnings fail).")) -> None:
        """Lint, tests, docs without warnings and the project's own checks; non-zero when one fails."""
        steps = []
        if lint:
            steps.append(("ruff", [sys.executable, "-m", "ruff", "check", *lint]))
        if tests is not None:
            steps.append(("tests", [sys.executable, "-m", "pytest", *tests]))
        if docs and docs_too:
            steps.append(("docs", [sys.executable, "-m", "sphinx", "-b", "html", "-q", "-W", root_path(docs),
                                   root_path(docs_out)]))
        failed = []
        for name, cmd in steps:
            typer.echo(f"── {name}")
            if subprocess.call(cmd, cwd=ROOT) != 0:
                failed.append(name)
        for name, fn in hooks(extra, WHERE):
            typer.echo(f"── {name}")
            problems = fn() or []
            for line in problems:
                typer.echo(f"  {line}")
            if problems:
                failed.append(name)
        typer.echo("all good" if not failed else f"failed: {', '.join(failed)}")
        raise typer.Exit(1 if failed else 0)

    app.command("check")(check)
