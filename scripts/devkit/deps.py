"""
List what the enabled tools need, print the dev extra, install it or check that it is present.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import re
import shutil
import subprocess
import sys
from typing import Any

import typer

from .config import REQUIRES as CORE
from .config import settings

__all__ = ["requirements", "externals", "merged", "missing", "register"]

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_PY_MARKER = re.compile(r"python_version\s*(<|<=|>|>=|==|!=)\s*['\"]([\d.]+)['\"]")
_COMPARE = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _name(requirement: str) -> str:
    match = _NAME.match(requirement)
    return re.sub(r"[-_.]+", "-", match.group(0)).lower() if match else requirement


def _applies(requirement: str) -> bool:
    """Whether the ``python_version`` marker of ``requirement`` (if any) holds for this interpreter."""
    marker = requirement.partition(";")[2]
    match = _PY_MARKER.search(marker)
    if match is None:
        return True
    wanted = tuple(int(p) for p in match.group(2).split("."))
    return _COMPARE[match.group(1)](sys.version_info[: len(wanted)], wanted)


def _modules() -> dict[str, Any]:
    """The enabled tools: table name -> imported module."""
    from . import GENERAL

    found = {}
    for key, module in GENERAL.items():
        if key in settings():
            found[key] = importlib.import_module(f"{__package__}.{module}")
    return found


def _tool_requirements(module: Any, cfg: dict[str, Any]) -> tuple[str, ...]:
    extra = getattr(module, "requires", None)
    return (*getattr(module, "REQUIRES", ()), *(extra(cfg) if extra else ()))


def requirements() -> dict[str, tuple[str, ...]]:
    """Requirement strings per source: ``"core"`` and each enabled tool."""
    found = {"core": tuple(CORE)}
    for key, module in _modules().items():
        found[key] = _tool_requirements(module, settings()[key])
    return found


def externals() -> dict[str, tuple[str, ...]]:
    """External programs per enabled tool."""
    return {key: tuple(getattr(m, "EXTERNAL", ())) for key, m in _modules().items() if getattr(m, "EXTERNAL", ())}


def merged(by_source: dict[str, tuple[str, ...]]) -> list[str]:
    """Every requirement once per package (the one with a version specifier wins), sorted."""
    chosen: dict[str, str] = {}
    for reqs in by_source.values():
        for req in reqs:
            name = _name(req)
            if name not in chosen or (not re.search(r"[<>=!~]", chosen[name]) and re.search(r"[<>=!~]", req)):
                chosen[name] = req
    return sorted(chosen.values(), key=lambda r: (_name(r), r))


def missing(reqs: list[str]) -> list[str]:
    """The requirements (that apply to this interpreter) whose package is not installed."""
    absent = []
    for req in reqs:
        if not _applies(req):
            continue
        try:
            importlib.metadata.version(_name(req))
        except importlib.metadata.PackageNotFoundError:
            absent.append(req)
    return absent


def register(app: typer.Typer) -> None:
    """Add the ``deps`` command (always available)."""

    def deps(
        install: bool = typer.Option(False, "--install", help="pip install every requirement into this interpreter."),
        check: bool = typer.Option(False, "--check", help="Exit 1 when a requirement is not installed."),
    ) -> None:
        """List what the enabled tools need and print a ready-to-paste dev extra."""
        by_source = requirements()
        reqs = merged(by_source)
        for source, items in by_source.items():
            typer.echo(f"{source}: {', '.join(items) or '-'}")
        outside = externals()
        for source, programs in outside.items():
            typer.echo(f"{source} (external): {', '.join(programs)}")
        typer.echo("")
        typer.echo("dev = [" + ", ".join(f'"{r}"' for r in reqs) + "]")
        absent_programs = sorted({p for programs in outside.values() for p in programs if shutil.which(p) is None})
        if absent_programs:
            typer.echo(f"not on PATH: {', '.join(absent_programs)}", err=True)
        if install:
            raise typer.Exit(subprocess.call([sys.executable, "-m", "pip", "install", *reqs]))
        if check:
            absent = missing(reqs)
            if absent:
                typer.echo(f"missing: {', '.join(absent)}", err=True)
                raise typer.Exit(1)
            typer.echo("all requirements installed")

    app.command("deps")(deps)
