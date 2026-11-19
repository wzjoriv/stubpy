"""Source files of installed (third-party) modules, found without importing anything."""
from __future__ import annotations

import importlib.machinery
import sys
from functools import lru_cache
from pathlib import Path

from . import vfs


@lru_cache(maxsize=256)
def _roots(top: str) -> tuple[Path, ...]:
    """Search folders for the top-level package *top*: its ``-stubs`` distribution first, then itself."""
    if top in sys.stdlib_module_names or top in sys.builtin_module_names:
        return ()
    found: list[Path] = []
    for entry in sys.path:
        stubs = Path(entry or ".") / f"{top}-stubs"
        if vfs.is_dir(stubs):
            found.append(stubs)
    try:
        spec = importlib.machinery.PathFinder.find_spec(top)
    except (ImportError, ValueError):
        spec = None
    if spec is not None:
        if spec.submodule_search_locations:
            found.extend(Path(p) for p in spec.submodule_search_locations)
        elif spec.origin and spec.origin.endswith((".py", ".pyi")):
            found.append(Path(spec.origin).parent)
    return tuple(found)


def installed_file(parts: list[str]) -> Path | None:
    """The ``.pyi`` or ``.py`` of the installed module ``".".join(parts)``; ``None`` when there is none.

    Only :class:`importlib.machinery.PathFinder` is asked, which reads the
    file system and never executes a package, and standard-library modules
    are left out.  A bundled stub (``.pyi`` next to the module or a
    ``<name>-stubs`` package) wins over the source.
    """
    if not parts:
        return None
    for root in _roots(parts[0]):
        package_root = root if root.name in (parts[0], f"{parts[0]}-stubs") else root / parts[0]
        if root.name not in (parts[0], f"{parts[0]}-stubs") and len(parts) == 1:
            for suffix in (".pyi", ".py"):
                if vfs.is_file(root / f"{parts[0]}{suffix}"):
                    return root / f"{parts[0]}{suffix}"
            continue
        target = package_root.joinpath(*parts[1:])
        for candidate in (target / "__init__.pyi", target / "__init__.py",
                          target.with_name(target.name + ".pyi"), target.with_name(target.name + ".py")):
            if vfs.is_file(candidate):
                return candidate
    return None
