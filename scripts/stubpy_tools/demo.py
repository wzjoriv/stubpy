"""``dev.py stubpy demo``: regenerate the demo package's stubs and report which ones changed."""

from __future__ import annotations

import typer

from ._common import DEMO, ROOT, use_local_stubpy

__all__ = ["demo"]


def demo(
    show: bool = typer.Option(False, "--show", help="Print every regenerated stub."),
) -> None:
    """Regenerate demo/*.pyi with this checkout's stubpy and list the stubs whose text changed."""
    use_local_stubpy()
    import stubpy

    before = {p: p.read_text(encoding="utf-8") for p in DEMO.glob("*.pyi")}
    result = stubpy.generate(DEMO)
    changed = [p for p in sorted(DEMO.glob("*.pyi")) if before.get(p) != p.read_text(encoding="utf-8")]
    for path in changed:
        typer.echo(f"changed  {path.relative_to(ROOT)}")
        if show:
            typer.echo(path.read_text(encoding="utf-8"))
    typer.echo(f"{result.summary()}  {len(changed)} changed")
    raise typer.Exit(1 if result.failed else 0)
