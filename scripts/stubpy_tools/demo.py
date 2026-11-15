"""``dev.py stubpy demo``: regenerate the svgwriter corpus stubs and report which ones changed."""

from __future__ import annotations

from pathlib import Path

import typer

from ._common import DEMO, DEMO_STUBS, ROOT, use_local_stubpy

__all__ = ["demo"]


def _snapshot(root: Path) -> dict[Path, str]:
    """Return ``{relative path: text}`` for every stub under *root*."""
    return {p.relative_to(root): p.read_text(encoding="utf-8") for p in root.rglob("*.pyi")} if root.is_dir() else {}


def demo(
    mode: str = typer.Option("runtime", "--mode", help="Execution mode: runtime, ast or auto."),
    show: bool = typer.Option(False, "--show", help="Print every changed stub."),
) -> None:
    """Regenerate demos/svgwriter stubs into build/dev/svgwriter-stubs and list the stubs that changed."""
    use_local_stubpy()
    import stubpy

    if not DEMO.is_dir():
        typer.echo(f"missing corpus: {DEMO.relative_to(ROOT)}", err=True)
        raise typer.Exit(2)
    before = _snapshot(DEMO_STUBS)
    report = stubpy.generate(DEMO, DEMO_STUBS, config=stubpy.Config(mode=mode))
    after = _snapshot(DEMO_STUBS)
    changed = sorted(p for p in after if before.get(p) != after[p])
    removed = sorted(set(before) - set(after))
    for rel in changed:
        typer.echo(f"{'new' if rel not in before else 'changed':8} {(DEMO_STUBS / rel).relative_to(ROOT)}")
        if show:
            typer.echo(after[rel])
    for rel in removed:
        typer.echo(f"gone     {(DEMO_STUBS / rel).relative_to(ROOT)}")
    for result in report.failed:
        for diagnostic in result.errors:
            typer.echo(f"error    {result.module_name}: {diagnostic.message}", err=True)
    typer.echo(f"{report.summary()}  {len(changed)} changed")
    raise typer.Exit(1 if report.failed else 0)
