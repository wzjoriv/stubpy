"""Console reporting for CLI runs."""
from __future__ import annotations

import sys

from stubpy.core.context import StubContext
from stubpy.core.results import PackageResult


def print_diagnostics(ctx: StubContext) -> None:
    """Print every diagnostic and a summary line to stderr."""
    print("\n--- Diagnostics ---", file=sys.stderr)
    for d in ctx.diagnostics:
        print(f"  {d}", file=sys.stderr)
    print(f"  Summary: {ctx.diagnostics.summary()}", file=sys.stderr)


def print_failures(result: PackageResult) -> None:
    """Print each failed file and its error diagnostics to stderr."""
    print("\nFailed files:", file=sys.stderr)
    for path, diags in result.failed:
        print(f"  {path}", file=sys.stderr)
        for d in diags:
            print(f"    {d}", file=sys.stderr)
