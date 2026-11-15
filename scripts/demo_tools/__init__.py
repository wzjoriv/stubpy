"""Developer commands for the demo projects, a group of ``scripts/dev.py``.

    python scripts/dev.py demos svgraster build          # build the native layers in place
    python scripts/dev.py demos svgraster fetch-suite    # download the W3C SVG 1.1 test suite
    python scripts/dev.py demos svgraster conformance    # score the renderer against the suite
"""

from __future__ import annotations

import typer

from .svgraster import app as svgraster_app

__all__ = ["app"]

app = typer.Typer(
    name="demos",
    help=__doc__.split("\n\n")[0],
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(svgraster_app, name="svgraster")
