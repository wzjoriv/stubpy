"""
Console reporting for CLI runs.
"""
from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

from stubpy.core.diagnostics import Level
from stubpy.core.results import Report, StubResult


class Printer:
    """Print run output: progress lines to stdout (unless quiet), diagnostics to stderr."""

    def __init__(self, quiet: bool, verbose: bool) -> None:
        self.quiet = quiet
        self.verbose = verbose and not quiet

    def line(self, text: str) -> None:
        """Print *text* to stdout unless quiet."""
        if not self.quiet:
            print(text)

    def diagnostics(self, report: Report) -> None:
        """Print the diagnostics of failed and skipped results (all results when verbose) to stderr."""
        failed = {id(r) for r in report.failed}
        for result in report:
            skipped = result.ok and not result.text and bool(result.warnings)
            self.result_diagnostics(result, force=id(result) in failed, skipped=skipped)

    def result_diagnostics(self, result: StubResult, force: bool = False, skipped: bool = False) -> None:
        """Print one result's diagnostics: ERRORs and WARNINGs when *force* or *skipped*, everything when verbose."""
        if self.verbose:
            shown = list(result.diagnostics)
        elif force or skipped:
            shown = [d for d in result.diagnostics if d.level >= Level.WARNING]
        else:
            return
        if not shown:
            return
        label = "FAILED" if force else "skipped" if skipped else "note"
        print(f"{label} {self.rel(result.source) if result.source else result.module_name}", file=sys.stderr)
        for d in shown:
            print(f"    {d}", file=sys.stderr)

    def diff(self, result: StubResult) -> str:
        """Return a unified diff from the stub on disk to the stub *result* would write."""
        path = result.output
        name = self.rel(path).replace(os.sep, "/") if path else result.module_name
        old = path.read_text(encoding="utf-8").splitlines(keepends=True) if path and path.is_file() else []
        lines = difflib.unified_diff(
            old, result.text.replace("\r\n", "\n").splitlines(keepends=True),
            fromfile=f"a/{name}" if old else "/dev/null", tofile=f"b/{name}",
        )
        return "".join(line if line.endswith("\n") else line + "\n" for line in lines)

    @staticmethod
    def rel(path: Path | None) -> str:
        """Return *path* relative to the working folder when it lies beneath it."""
        if path is None:
            return ""
        try:
            return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(path)
