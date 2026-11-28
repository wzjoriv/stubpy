"""
Notebooks tool: build Jupyter notebooks (with outputs) from plain .py examples split at ``# %%`` markers.
"""

from __future__ import annotations

import ast
import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer

from .config import ConfigError, root_path, typed
from .paths import shown

__all__ = ["cells_of", "notebook_of", "register"]

WHERE = "tool.devkit.notebooks"
REQUIRES: tuple[str, ...] = ("nbformat", "nbclient", "ipykernel")
EXTERNAL: tuple[str, ...] = ()
MISSING = "pip install nbformat nbclient ipykernel (add them to your dev extra)"

MARKER = "# %%"
MARKDOWN_TAG = "[markdown]"
DEFAULT_SOURCE = "examples"
DEFAULT_PATTERN = "*.py"
DEFAULT_TIMEOUT = 600
DEFAULT_KERNEL = "python3"
NBFORMAT = 4
NBFORMAT_MINOR = 5
_HELP = {"help_option_names": ["-h", "--help"]}


def _docstring_split(text: str) -> tuple[str | None, str]:
    """The module docstring of *text* (or None) and the code after it."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None, text
    first = tree.body[0] if tree.body else None
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str) and first.end_lineno is not None):
        rest = text.splitlines(keepends=True)[first.end_lineno:]
        return ast.get_docstring(tree), "".join(rest)
    return None, text


def _markdown(lines: list[str]) -> str:
    """Comment lines of a ``# %% [markdown]`` cell without their leading ``#``."""
    out = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("# "):
            out.append(stripped[2:])
        elif stripped.startswith("#"):
            out.append(stripped[1:])
        else:
            out.append(stripped)
    return "\n".join(out).strip("\n")


def cells_of(text: str) -> list[tuple[str, str]]:
    """Split a script into ``(kind, source)`` cells: ``"markdown"`` or ``"code"``.

    The module docstring becomes the first markdown cell. ``# %%`` starts a code cell (text after the
    marker on that line is kept as a comment) and ``# %% [markdown]`` a markdown cell written as comments.
    A script without markers is one code cell. Empty cells are dropped.
    """
    doc, code = _docstring_split(text)
    cells: list[tuple[str, str]] = [("markdown", doc.strip())] if doc and doc.strip() else []
    kind, block = "code", []

    def close() -> None:
        body = _markdown(block) if kind == "markdown" else "".join(block).strip("\n")
        if body.strip():
            cells.append((kind, body))

    for line in code.splitlines(keepends=True):
        if line.startswith(MARKER):
            close()
            title = line[len(MARKER):].strip()
            kind = "markdown" if title.startswith(MARKDOWN_TAG) else "code"
            block = [] if kind == "markdown" or not title else [f"# {title}\n"]
            continue
        block.append(line)
    close()
    return cells


def notebook_of(text: str, kernel: str = DEFAULT_KERNEL) -> dict[str, Any]:
    """An nbformat 4 notebook (as a dict, no outputs) for a script, with stable cell ids."""
    cells = []
    for index, (kind, source) in enumerate(cells_of(text)):
        cell: dict[str, Any] = {"cell_type": kind, "id": f"cell-{index}", "metadata": {}, "source": source}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    return {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": kernel},
                     "language_info": {"name": "python"}},
        "nbformat": NBFORMAT,
        "nbformat_minor": NBFORMAT_MINOR,
    }


def _sources(notebook: dict[str, Any]) -> list[tuple[str, str]]:
    """The ``(kind, source)`` of every cell, sources joined, for comparing notebooks without their outputs."""
    out = []
    for cell in notebook.get("cells", []):
        source = cell.get("source", "")
        out.append((cell.get("cell_type", ""), "".join(source) if isinstance(source, list) else source))
    return out


def _drop(outputs: list[dict[str, Any]], drop: list[str]) -> None:
    """Remove the *drop* mimetypes from rich outputs that would still show something else."""
    for output in outputs:
        data = output.get("data")
        if not data:
            continue
        kept = {kind: value for kind, value in data.items() if kind not in drop}
        if any(kind != "text/plain" for kind in kept) or not any(kind != "text/plain" for kind in data):
            output["data"] = kept


def _execute(notebook: dict[str, Any], workdir: Path, timeout: int, kernel: str,
             drop: list[str]) -> dict[str, Any]:
    """Run *notebook* in *workdir* and return it with outputs, stripped of run-specific metadata."""
    try:
        import nbformat
        from nbclient import NotebookClient
    except ImportError as exc:
        typer.echo(MISSING, err=True)
        raise typer.Exit(2) from exc
    node = nbformat.from_dict(notebook)
    NotebookClient(node, timeout=timeout, kernel_name=kernel, resources={"metadata": {"path": str(workdir)}}).execute()
    result = json.loads(nbformat.writes(node))
    for cell in result["cells"]:
        cell.get("metadata", {}).pop("execution", None)
        _drop(cell.get("outputs", []), drop)
    result["metadata"] = notebook["metadata"]
    return result


def _dump(notebook: dict[str, Any]) -> str:
    return json.dumps(notebook, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``notebooks`` command group, configured by ``[tool.devkit.notebooks]`` (``cfg``)."""
    source = Path(root_path(typed(cfg, "source", str, DEFAULT_SOURCE, WHERE)))
    out = Path(root_path(typed(cfg, "out", str, str(source), WHERE)))
    pattern = typed(cfg, "pattern", str, DEFAULT_PATTERN, WHERE)
    exclude = typed(cfg, "exclude", list, [], WHERE)
    timeout = typed(cfg, "timeout", int, DEFAULT_TIMEOUT, WHERE)
    kernel = typed(cfg, "kernel", str, DEFAULT_KERNEL, WHERE)
    execute = typed(cfg, "execute", bool, True, WHERE)
    drop = typed(cfg, "drop", list, [], WHERE)
    if not all(isinstance(name, str) for name in exclude):
        raise ConfigError(f"[{WHERE}] exclude must be a list of file names")
    if not all(isinstance(kind, str) for kind in drop):
        raise ConfigError(f"[{WHERE}] drop must be a list of mimetypes such as 'image/png'")
    group = typer.Typer(help="Build Jupyter notebooks from the .py examples (cells split at '# %%').",
                        no_args_is_help=True, add_completion=False, context_settings=_HELP)

    def scripts(names: list[str] | None) -> list[Path]:
        found = [p for p in sorted(source.glob(pattern)) if p.name not in exclude and not p.name.startswith("_")]
        if names:
            found = [p for p in found if p.stem in names or p.name in names or p.parent.name in names]
        return found

    def target(script: Path) -> Path:
        """Beside the script when notebooks go to the source folder (one folder per example), else in *out*."""
        return script.with_suffix(".ipynb") if out == source else out / f"{script.stem}.ipynb"

    def workspace(script: Path, work: Path) -> Path:
        """Where the notebook runs: a copy of the script's own folder when it has one, so it can read its files."""
        if script.parent != source:
            shutil.copytree(script.parent, work, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.ipynb", "__pycache__"))
        return work

    @group.command("build")
    def build(
        names: Annotated[list[str] | None, typer.Argument(help="Only these scripts (stem, file or folder name).")] = None,
        no_run: Annotated[bool, typer.Option("--no-run", help="Write the cells without running them.")] = False,
    ) -> None:
        """Write each script's notebook (beside it, or in <out>), run so the outputs are saved."""
        chosen = scripts(names)
        out.mkdir(parents=True, exist_ok=True)
        for script in chosen:
            notebook = notebook_of(script.read_text(encoding="utf-8"), kernel)
            if execute and not no_run:
                with tempfile.TemporaryDirectory(prefix="devkit-nb-") as work:
                    notebook = _execute(notebook, workspace(script, Path(work)), timeout, kernel, drop)
            written = target(script)
            written.write_text(_dump(notebook), encoding="utf-8", newline="\n")
            typer.echo(f"wrote {shown(written)}")
        typer.echo(f"{len(chosen)} notebook(s) built")

    @group.command("check")
    def check() -> None:
        """Exit 1 when a notebook is missing or its cells differ from its script (outputs are not compared)."""
        stale = []
        for script in scripts(None):
            notebook = target(script)
            want = _sources(notebook_of(script.read_text(encoding="utf-8"), kernel))
            have = _sources(json.loads(notebook.read_text(encoding="utf-8"))) if notebook.is_file() else None
            if have != want:
                stale.append(notebook)
                typer.echo(f"stale: {shown(notebook)}", err=True)
        if stale:
            typer.echo(f"{len(stale)} notebook(s) out of date: run `notebooks build`", err=True)
            raise typer.Exit(1)
        typer.echo("notebooks up to date")

    app.add_typer(group, name="notebooks")
