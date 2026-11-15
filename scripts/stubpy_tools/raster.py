"""``dev.py stubpy raster``: stub the svgraster demo (pure modules and its compiled extensions) and report."""

from __future__ import annotations

import ast
import shutil

import typer

from ._common import BUILD, RASTER, ROOT, use_local_stubpy

__all__ = ["raster"]

#: Where ``dev.py stubpy raster`` writes the stubs
RASTER_STUBS = BUILD / "svgraster-stubs"


def raster(
    docstrings: bool = typer.Option(False, "--docstrings", help="Use runtime docstrings as stub bodies."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="List every warning and INFO note."),
) -> None:
    """Generate stubs for demos/svgraster/svgraster into build/dev/svgraster-stubs; non-zero on failures."""
    use_local_stubpy()
    import stubpy
    from stubpy.compiled.detect import is_extension_file

    if not RASTER.is_dir():
        typer.echo(f"missing demo: {RASTER.relative_to(ROOT)}", err=True)
        raise typer.Exit(2)
    shutil.rmtree(RASTER_STUBS, ignore_errors=True)
    report = stubpy.generate(RASTER, RASTER_STUBS, config=stubpy.Config(include_docstrings=docstrings))
    bad = []
    for stub in RASTER_STUBS.rglob("*.pyi"):
        try:
            ast.parse(stub.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            bad.append(f"{stub.relative_to(RASTER_STUBS)}: {exc}")
    compiled = [r for r in report if r.source is not None and is_extension_file(r.source)]
    for result in compiled:
        state = "stubbed" if result.output is not None and result.ok else "skipped"
        overloads = result.text.count("@overload")
        typer.echo(f"{state:8} {result.module_name:24} {len(result.text.splitlines()):4} lines  {overloads:3} overloads")
        for d in result.diagnostics:
            if verbose or d.level.name != "INFO":
                typer.echo(f"         {d}")
    for result in report.failed:
        for d in result.errors:
            typer.echo(f"error    {result.module_name}: {d.message}", err=True)
    for line in bad:
        typer.echo(f"unparsable {line}", err=True)
    typer.echo(f"{report.summary()}  {len(compiled)} compiled  {len(bad)} unparsable  -> {RASTER_STUBS.relative_to(ROOT)}")
    raise typer.Exit(1 if report.failed or bad else 0)
