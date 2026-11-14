"""``dev.py stubpy self-stub``: stub stubpy's own package in each execution mode into ``build/dev``.

A smoke test on a real, non-trivial package: it fails when any file errors or a stub is not valid Python.
"""

from __future__ import annotations

import ast
import shutil

import typer

from ._common import BUILD, ROOT, use_local_stubpy

__all__ = ["self_stub"]

MODES = ("runtime", "ast_only")


def self_stub(
    keep: bool = typer.Option(False, "--keep", help="Keep the output in build/dev instead of deleting it."),
) -> None:
    """Stub the stubpy package in every execution mode; non-zero when a file fails or a stub does not parse."""
    use_local_stubpy()
    from stubpy import ExecutionMode, StubConfig, generate_package

    failures = 0
    for mode in MODES:
        out = BUILD / f"self-{mode}"
        shutil.rmtree(out, ignore_errors=True)
        result = generate_package(ROOT / "stubpy", out, config=StubConfig(execution_mode=ExecutionMode(mode)))
        bad = []
        for stub in out.rglob("*.pyi"):
            try:
                ast.parse(stub.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                bad.append(f"{stub.relative_to(out)}: {exc}")
        typer.echo(f"── {mode}: {result.summary()}  {len(bad)} unparsable")
        for line in bad:
            typer.echo(f"  {line}")
        failures += len(result.failed) + len(bad)
        if not keep:
            shutil.rmtree(out, ignore_errors=True)
    raise typer.Exit(1 if failures else 0)
