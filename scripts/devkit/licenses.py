"""``dev.py licenses``: download the licence texts a TOML catalogue lists, one ``<id>.txt`` each (git-ignored;
ship them as package data so wheels and executables carry them).

    [tool.devkit.licenses]
    catalogue = "mypkg/about/licenses.toml"   # [[<any kind>]] tables with id and text (a plain-text URL)
    out = "mypkg/about/licenses"
    user_agent = "mypkg-dev (https://example.org)"

    python scripts/dev.py licenses           # missing ones only
    python scripts/dev.py licenses --all     # every one again
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import typer

from .config import ConfigError, project_name, root_path, tomllib, typed

__all__ = ["register", "entries"]

WHERE = "tool.devkit.licenses"
TIMEOUT_S = 30


def entries(catalogue: Path) -> list[dict[str, Any]]:
    """Every table of the catalogue's arrays of tables (whatever their kind) that has an ``id``."""
    with open(catalogue, "rb") as f:
        data = tomllib.load(f)
    return [e for value in data.values() if isinstance(value, list) for e in value
            if isinstance(e, dict) and e.get("id")]


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``licenses`` command, configured by ``[tool.devkit.licenses]`` (``cfg``)."""
    if "catalogue" not in cfg or "out" not in cfg:
        raise ConfigError(f"[{WHERE}] needs catalogue and out")
    catalogue = Path(root_path(typed(cfg, "catalogue", str, "", WHERE)))
    out = Path(root_path(typed(cfg, "out", str, "", WHERE)))
    agent = typed(cfg, "user_agent", str, f"{project_name()}-dev", WHERE)

    def licenses(all_: bool = typer.Option(False, "--all", help="Download again even if the file exists.")) -> None:
        """Download the licence texts the catalogue lists."""
        out.mkdir(parents=True, exist_ok=True)
        failed = 0
        for item in entries(catalogue):
            url = str(item.get("text") or "").strip()
            if not url:
                continue
            path = out / f"{item['id']}.txt"
            if path.is_file() and not all_:
                print(f"  have  {item['id']}")
                continue
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": agent}),
                                            timeout=TIMEOUT_S) as r:
                    text = r.read().decode("utf-8", errors="replace")
            except (urllib.error.URLError, OSError) as exc:
                failed += 1
                print(f"  FAIL  {item['id']}: {exc}", file=sys.stderr)
                continue
            path.write_text(text, encoding="utf-8")
            print(f"  got   {item['id']}  ({len(text):,} chars)")
        if failed:
            raise typer.Exit(1)

    app.command("licenses")(licenses)
