"""
Names each module of a run must keep in its stub because a sibling module imports them.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from stubpy.resolve.static import SourceIndex

from ._parsed import parse_file


def requested_names(sources: Iterable[Path], index: SourceIndex) -> dict[Path, set[str]]:
    """Map each module file of *sources* to the names the other modules import from it.

    Each file is parsed and harvested once into *index*, which also keeps what the
    pipeline needs from the parse (``index.parsed``) until the file is rendered.
    """
    paths = [Path(s).resolve() for s in sources]
    wanted = set(paths)
    for path in paths:
        if index.harvested(path) is None:
            symbols, parsed = parse_file(path)
            index.record(path, symbols)
            if parsed is not None:
                index.parsed[path] = parsed
    found: dict[Path, set[str]] = {}
    for path in paths:
        current = index.module_at(path)
        if current is None:
            continue
        for imp in current.symbols.imports:
            if imp.module is None or imp.name == "*":
                continue
            there = index.import_path(current, imp.module)
            if there in wanted and there != path and index.harvested(there) is not None:
                found.setdefault(there, set()).add(imp.name)
    return found
