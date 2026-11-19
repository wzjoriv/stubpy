"""``dev.py stubpy self-stub``: stub stubpy's own package with and without importing it into ``build/dev``.

A smoke test on a real, non-trivial package: it fails when any file errors or a stub is not valid Python.
"""

from __future__ import annotations

import ast
import shutil

import typer

from ._common import BUILD, ROOT, use_local_stubpy

__all__ = ["self_stub"]

RUNS = {"default": {}, "no-import": {"imports": "none"}}


def self_stub(
    keep: bool = typer.Option(False, "--keep", help="Keep the output in build/dev instead of deleting it."),
) -> None:
    """Stub the stubpy package by default and with --no-import; non-zero when a file fails or a stub does not parse."""
    use_local_stubpy()
    import stubpy

    failures = 0
    for run, options in RUNS.items():
        out = BUILD / f"self-{run}"
        shutil.rmtree(out, ignore_errors=True)
        result = stubpy.generate(ROOT / "stubpy", out, config=stubpy.Config(**options))
        bad = []
        for stub in out.rglob("*.pyi"):
            try:
                ast.parse(stub.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                bad.append(f"{stub.relative_to(out)}: {exc}")
        for failed in result.failed:
            typer.echo(f"  failed {failed.module_name}: {'; '.join(d.message for d in failed.errors)}")
        typer.echo(f"── {run}: {result.summary()}  {len(bad)} unparsable")
        for line in bad:
            typer.echo(f"  {line}")
        failures += len(result.failed) + len(bad)
        if not keep:
            shutil.rmtree(out, ignore_errors=True)
    raise typer.Exit(1 if failures else 0)
