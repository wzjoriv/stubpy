"""stubpy's own developer commands, a group of ``scripts/dev.py``.

    python scripts/dev.py stubpy demo              # regenerate demo/*.pyi and list what changed
    python scripts/dev.py stubpy self-stub         # stub stubpy itself in every execution mode (smoke test)
"""

from __future__ import annotations

import typer

from .demo import demo
from .self_stub import self_stub

__all__ = ["app"]

app = typer.Typer(
    name="stubpy",
    help=__doc__.split("\n\n")[0],
    no_args_is_help=True,
    add_completion=False,
)
app.command("demo")(demo)
app.command("self-stub")(self_stub)
