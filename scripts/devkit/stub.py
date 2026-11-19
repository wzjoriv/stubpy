"""
Stub tools: write and check .pyi stubs and sync compiled-module docstrings into them, all through stubpy.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from typing import Annotated, Any

import typer

from .config import typed
from .paths import ROOT

__all__ = ["register"]

WHERE = "tool.devkit.stub"
REQUIRES: tuple[str, ...] = ("stubpy",)
EXTERNAL: tuple[str, ...] = ()
MISSING = "pip install stubpy (add it to your dev extra)"
_HELP = {"help_option_names": ["-h", "--help"]}


def _stubpy(argv: list[str]) -> int:
    """Run ``python -m stubpy <argv>`` from the repository root; exit 2 with a clear message when stubpy is absent."""
    if importlib.util.find_spec("stubpy") is None:
        typer.echo(MISSING, err=True)
        raise typer.Exit(2)
    return subprocess.call([sys.executable, "-m", "stubpy", *argv], cwd=ROOT)


def _has_list_command() -> bool:
    """Whether this stubpy's ``docstrings`` command offers ``list``."""
    out = subprocess.run([sys.executable, "-m", "stubpy", "docstrings", "--help"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return "list" in out.stdout.split("positional arguments:")[-1].split("options:")[0]


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``stub`` command group, configured by ``[tool.devkit.stub]`` (``cfg``)."""
    targets = [str(t) for t in typed(cfg, "targets", list, [], WHERE)]
    output = typed(cfg, "output", str, "", WHERE)
    args = [str(a) for a in typed(cfg, "args", list, [], WHERE)]
    doc_args = [str(a) for a in typed(cfg, "docstring_args", list, [], WHERE)]
    base = [*(["-o", output] if output else []), *args]

    group = typer.Typer(help="Write, check and docstring-sync .pyi stubs (stubpy).", no_args_is_help=True,
                        add_completion=False, context_settings=_HELP)
    docstrings = typer.Typer(help="Copy compiled modules' docstrings into hand-written stubs.",
                             no_args_is_help=True, add_completion=False, context_settings=_HELP)

    @group.command("generate")
    def generate() -> None:
        """Write the stubs of the configured targets (stubpy generate)."""
        raise typer.Exit(_stubpy(["generate", *targets, *base]))

    @group.command("check")
    def check() -> None:
        """Exit 1 when the stubs on disk are stale, showing the diff (stubpy check --diff)."""
        raise typer.Exit(_stubpy(["check", "--diff", *targets, *base]))

    def docstring_command(action: str, summary: str) -> None:
        def command(extra: Annotated[list[str] | None, typer.Argument(help="Stub files or folders.")] = None) -> None:
            verb = action
            if action == "list" and not _has_list_command():
                verb = "check"
            raise typer.Exit(_stubpy(["docstrings", verb, *(extra or doc_args)]))

        command.__doc__ = summary
        docstrings.command(action, context_settings={**_HELP, "ignore_unknown_options": True})(command)

    docstring_command("sync", "Write the docstrings of the compiled modules into their stubs.")
    docstring_command("check", "Exit 1 when a stub's docstrings are out of date.")
    docstring_command("list", "List the stubs and modules paired (older stubpy: same as check).")
    group.add_typer(docstrings, name="docstrings")
    app.add_typer(group, name="stub")
