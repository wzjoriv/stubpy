"""
Type-checking the written stubs with mypy (or pyright) and attaching each error to its stub's result.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from stubpy.config.options import Config
from stubpy.state.diagnostics import Diagnostic, Level, Stage

from .results import Report

_MYPY_LINE = re.compile(r"^(?P<path>.+?\.pyi):(?P<line>\d+): error: (?P<message>.*?)(?:\s+\[(?P<code>[\w-]+)\])?$")
_PYRIGHT_LINE = re.compile(r"^\s*(?P<path>.+?\.pyi):(?P<line>\d+):\d+ - error: (?P<message>.*?)(?: \((?P<code>\w+)\))?$")


def typecheck(report: Report, config: Config) -> Report:
    """Run a type checker over the stubs of *report* and add one WARNING per error to the stub's result.

    mypy is used when it is importable, else ``pyright`` when it is on ``PATH``. Without either,
    ``report.typecheck_note`` says so and nothing else changes.

    Parameters
    ----------
    report : Report
        The finished run; its results' ``output`` paths are checked as they are on disk.
    config : Config
        The run options; ``target_python`` is the version checked against.

    Returns
    -------
    Report
        *report*, its results carrying the type errors.
    """
    paths = sorted({r.output.resolve() for r in report.results if r.ok and r.output is not None and r.output.is_file()})
    if not paths:
        return report
    found = _run(paths, config.target_python)
    if found is None:
        report.typecheck_note = "type check skipped: install mypy (or pyright) for --typecheck"
        return report
    checker, errors = found
    by_path: dict[Path, list[Diagnostic]] = {}
    for path, line, message, code in errors:
        text = f"{checker}: line {line}: {message}" + (f" [{code}]" if code else "")
        by_path.setdefault(path, []).append(Diagnostic(Level.WARNING, Stage.TYPECHECK, path.name, text))
    report.results = [
        replace(r, diagnostics=(*r.diagnostics, *by_path[r.output.resolve()]))
        if r.output is not None and r.output.resolve() in by_path else r
        for r in report.results
    ]
    report.type_errors = sum(len(v) for v in by_path.values())
    return report


def _run(paths: list[Path], version: str) -> tuple[str, list[tuple[Path, str, str, str | None]]] | None:
    """``(checker, [(stub, line, message, code)])`` from mypy or pyright; ``None`` when neither is available."""
    root = Path(os.path.commonpath([str(p.parent) for p in paths]))
    if importlib.util.find_spec("mypy") is not None:
        with tempfile.TemporaryDirectory() as cache:
            out = subprocess.run(
                [sys.executable, "-m", "mypy", *map(str, paths), "--no-error-summary", "--hide-error-context",
                 "--show-error-codes", "--follow-imports", "silent", "--python-version", version,
                 "--cache-dir", cache, "--no-color-output"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            ).stdout
        return "mypy", _parse(out, _MYPY_LINE, root)
    pyright = shutil.which("pyright")
    if pyright is not None:
        out = subprocess.run([pyright, "--pythonversion", version, *map(str, paths)], cwd=root,
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        return "pyright", _parse(out, _PYRIGHT_LINE, root)
    return None


def _parse(output: str, pattern: re.Pattern[str], root: Path) -> list[tuple[Path, str, str, str | None]]:
    """The errors in a checker's *output*, paths made absolute against *root*.

    Examples
    --------
    >>> _parse("pkg\\\\m.pyi:3: error: Name \\"x\\" is not defined  [name-defined]", _MYPY_LINE, Path("/r"))[0][1:]
    ('3', 'Name "x" is not defined', 'name-defined')
    """
    found = []
    for line in output.splitlines():
        m = pattern.match(line.strip())
        if m:
            path = Path(m["path"])
            found.append(((path if path.is_absolute() else root / path).resolve(), m["line"], m["message"], m["code"]))
    return found
