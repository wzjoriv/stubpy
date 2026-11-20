"""stubpy's own developer commands, a group of ``scripts/dev.py``.

    python scripts/dev.py stubpy corpus              # regenerate the svgwriter corpus stubs and list what changed
    python scripts/dev.py stubpy self-stub         # stub stubpy itself, default and --no-import (smoke test)
    python scripts/dev.py stubpy raster            # stub the svgraster corpus, compiled extensions included
"""

from __future__ import annotations

import typer

from .corpus import corpus
from .raster import raster
from .self_stub import self_stub

__all__ = ["app"]

app = typer.Typer(
    name="stubpy",
    help=__doc__.split("\n\n")[0],
    no_args_is_help=True,
    add_completion=False,
)
app.command("corpus")(corpus)
app.command("self-stub")(self_stub)
app.command("raster")(raster)
