"""svgraster's developer command: build the native modules in place.

    python scripts/dev.py corpora svgraster build          # build the native modules, single-threaded
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import typer

__all__ = ["app"]

#: The repository root (``scripts/corpora_tools/svgraster.py`` is two folders below it)
ROOT = Path(__file__).resolve().parents[2]
#: The svgraster project folder
PROJECT = ROOT / "corpora" / "svgraster"

app = typer.Typer(
    name="svgraster",
    help=__doc__.split("\n\n")[0],
    no_args_is_help=True,
    add_completion=False,
)


@app.command("build")
def build(
    clean: bool = typer.Option(False, "--clean", help="Remove the build folder first."),
) -> None:
    """Build svgraster's native modules in place (single-threaded)."""
    if clean:
        shutil.rmtree(PROJECT / "build", ignore_errors=True)
    code = subprocess.call([sys.executable, "setup.py", "build_ext", "--inplace", "-j", "1"], cwd=PROJECT)
    raise typer.Exit(code)
