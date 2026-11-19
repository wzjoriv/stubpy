"""
Turn each standalone TikZ .tex of the docs' pictures into an .svg next to it.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer

from .config import root_path, typed
from .paths import shown

__all__ = ["register"]

WHERE = "tool.devkit.diagrams"
TOOLS = ("latex", "dvisvgm")
REQUIRES: tuple[str, ...] = ()
EXTERNAL: tuple[str, ...] = TOOLS


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``diagrams`` command, configured by ``[tool.devkit.diagrams]`` (``cfg``)."""
    images = Path(root_path(typed(cfg, "images", str, "docs/_static/images", WHERE)))

    def diagrams() -> None:
        """Every TikZ .tex of the docs' pictures as an .svg next to it."""
        missing = [t for t in TOOLS if shutil.which(t) is None]
        if missing:
            typer.echo(f"needs {' and '.join(missing)} (a TeX distribution: TeX Live, MiKTeX)")
            raise typer.Exit(1)
        failed = []
        for tex in sorted(images.glob("*.tex")):
            with tempfile.TemporaryDirectory() as work:
                run = subprocess.run(["latex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={work}",
                                      str(tex)], capture_output=True, text=True)
                dvi = Path(work, f"{tex.stem}.dvi")
                if run.returncode != 0 or not dvi.exists():
                    failed.append(tex.stem)
                    typer.echo(f"{tex.name}: LaTeX failed:\n" + "\n".join(
                        line for line in run.stdout.splitlines() if line.startswith(("!", "l."))))
                    continue
                svg = tex.with_suffix(".svg")
                subprocess.run(["dvisvgm", "--no-fonts", "--exact-bbox", str(dvi), "-o", str(svg)], capture_output=True,
                               check=True)
                typer.echo(f"wrote {shown(svg)}")
        if failed:
            raise typer.Exit(1)

    app.command("diagrams")(diagrams)
