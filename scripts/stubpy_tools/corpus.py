"""``dev.py stubpy corpus``: regenerate the drawlib corpus stubs and report which ones changed."""

from __future__ import annotations

from pathlib import Path

import typer

from ._common import CORPUS, CORPUS_STUBS, ROOT, use_local_stubpy

__all__ = ["corpus"]


def _snapshot(root: Path) -> dict[Path, str]:
    """Return ``{relative path: text}`` for every stub under *root*."""
    return {p.relative_to(root): p.read_text(encoding="utf-8") for p in root.rglob("*.pyi")} if root.is_dir() else {}


def corpus(
    no_import: bool = typer.Option(False, "--no-import", help="Source analysis only; import nothing."),
    show: bool = typer.Option(False, "--show", help="Print every changed stub."),
) -> None:
    """Regenerate corpora/drawlib stubs into build/dev/drawlib-stubs and list the stubs that changed."""
    use_local_stubpy()
    import stubpy

    if not CORPUS.is_dir():
        typer.echo(f"missing corpus: {CORPUS.relative_to(ROOT)}", err=True)
        raise typer.Exit(2)
    before = _snapshot(CORPUS_STUBS)
    report = stubpy.generate(CORPUS, CORPUS_STUBS, config=stubpy.Config(imports="none" if no_import else "all"))
    after = _snapshot(CORPUS_STUBS)
    changed = sorted(p for p in after if before.get(p) != after[p])
    removed = sorted(set(before) - set(after))
    for rel in changed:
        typer.echo(f"{'new' if rel not in before else 'changed':8} {(CORPUS_STUBS / rel).relative_to(ROOT)}")
        if show:
            typer.echo(after[rel])
    for rel in removed:
        typer.echo(f"gone     {(CORPUS_STUBS / rel).relative_to(ROOT)}")
    for result in report.failed:
        for diagnostic in result.errors:
            typer.echo(f"error    {result.module_name}: {diagnostic.message}", err=True)
    typer.echo(f"{report.summary()}  {len(changed)} changed")
    raise typer.Exit(1 if report.failed else 0)
