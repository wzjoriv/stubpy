"""Developer commands for the test corpora, a group of ``scripts/dev.py``.

    python scripts/dev.py corpora svgraster build          # build the native modules in place
"""

from __future__ import annotations

import typer

from .svgraster import app as svgraster_app

__all__ = ["app"]

app = typer.Typer(
    name="corpora",
    help=__doc__.split("\n\n")[0],
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(svgraster_app, name="svgraster")
