"""
Where a file imports from, and the interpreter state set around one import.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

from stubpy._constants import SOURCE_ROOT_NAMES
from stubpy.compiled.detect import module_stem

from . import vfs


class ImportTarget(NamedTuple):
    """Where a file is importable from: the ``sys.path`` root and the dotted module name."""
    root: Path
    name: str


def same_file(a: str | os.PathLike, b: str | os.PathLike) -> bool:
    """Return ``True`` when *a* and *b* name the same file."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _is_package_dir(folder: Path) -> bool:
    return vfs.is_file(folder / "__init__.py")


def _is_namespace_dir(folder: Path, root: Path | None) -> bool:
    """Return ``True`` for a folder without ``__init__.py`` strictly beneath the explicit *root*."""
    if root is None or folder == root or root not in folder.parents:
        return False
    return folder.name.isidentifier() and folder.name not in SOURCE_ROOT_NAMES


def find_import_target(path: str | Path, root: str | Path | None = None) -> ImportTarget | None:
    """Return the import root and dotted name of *path*, or ``None`` for a loose script.

    Folders with an ``__init__.py`` are packages.  Beneath an explicit *root*,
    folders without one are treated as namespace packages, except ``src``-style
    source roots.  A module at the top of a zip archive imports from the archive.

    Examples
    --------
    >>> find_import_target("/tmp/no_such_dir/script.py") is None
    True
    """
    file = Path(path).resolve()
    root_dir = Path(root).resolve() if root is not None else None
    parts = [] if file.name == "__init__.py" else [module_stem(file)]
    folder = file.parent
    while _is_package_dir(folder) or _is_namespace_dir(folder, root_dir):
        parts.insert(0, folder.name)
        folder = folder.parent
    if len(parts) < 2 and file.name != "__init__.py" and not folder.is_file():
        return None
    if not parts or not all(p.isidentifier() for p in parts):
        return None
    return ImportTarget(folder, ".".join(parts))


class ImportState:
    """Context manager that sets ``sys.path``, ``sys.argv`` and bytecode writing for one import."""

    def __init__(self, path: Path, roots: list[str]) -> None:
        self._path = path
        self._roots = roots

    def __enter__(self) -> None:
        self._saved_path = list(sys.path)
        self._saved_argv = list(sys.argv)
        self._saved_bytecode = sys.dont_write_bytecode
        sys.path[:0] = [r for r in self._roots if r not in sys.path[: len(self._roots)]]
        sys.argv = [str(self._path)]
        sys.dont_write_bytecode = True

    def __exit__(self, *exc: object) -> None:
        sys.path[:] = self._saved_path
        sys.argv = self._saved_argv
        sys.dont_write_bytecode = self._saved_bytecode
