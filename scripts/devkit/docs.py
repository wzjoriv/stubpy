"""``dev.py docs``: build the HTML docs with Sphinx, after the project's own steps (generated tables).

    [tool.devkit.docs]
    source = "docs"
    out = "docs/_build/html"
    before = ["reference.tables:refresh"]   # run first; a failing one is reported and the build goes on
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

import typer

from .config import root_path, typed
from .hooks import hooks
from .paths import ROOT

__all__ = ["register"]

WHERE = "tool.devkit.docs"


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``docs`` command, configured by ``[tool.devkit.docs]`` (``cfg``)."""
    source = root_path(typed(cfg, "source", str, "docs", WHERE))
    out = root_path(typed(cfg, "out", str, "docs/_build/html", WHERE))
    before = typed(cfg, "before", list, [], WHERE)

    def docs(clean: bool = typer.Option(False, help="Rebuild every page (after theme or layout changes)."),
             open_: bool = typer.Option(False, "--open", help="Open the result in the browser."),
             steps: bool = typer.Option(True, "--steps/--no-steps", help="Run the project's steps first.")) -> None:
        """Build the HTML docs (Sphinx)."""
        for name, fn in hooks(before, WHERE) if steps else []:
            try:
                fn()
            except (Exception, SystemExit) as exc:          # e.g. no display: build with what is there
                typer.echo(f"{name} skipped ({exc}); building with the files as they are")
        if clean:
            shutil.rmtree(Path(out).parent, ignore_errors=True)
        code = subprocess.call([sys.executable, "-m", "sphinx", "-b", "html", "-q", source, out], cwd=ROOT)
        if code == 0 and open_:
            webbrowser.open(Path(out, "index.html").as_uri())
        raise typer.Exit(code)

    app.command("docs")(docs)
