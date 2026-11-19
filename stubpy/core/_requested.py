"""
Names each module of a run must keep in its stub because a sibling module imports them.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from stubpy.resolve.static import SourceIndex


def requested_names(sources: Iterable[Path], index: SourceIndex) -> dict[Path, set[str]]:
    """Map each module file of *sources* to the names the other modules import from it."""
    paths = [Path(s).resolve() for s in sources]
    wanted = set(paths)
    found: dict[Path, set[str]] = {}
    for path in paths:
        current = index.module_at(path)
        if current is None:
            continue
        for imp in current.symbols.imports:
            if imp.module is None or imp.name == "*":
                continue
            there = index.import_from(current, imp.module)
            if there is not None and there.path in wanted and there.path != path:
                found.setdefault(there.path, set()).add(imp.name)
    return found
