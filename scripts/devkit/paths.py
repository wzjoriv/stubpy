"""Where the developer tools work: the repository root (the nearest folder above this file holding a
``pyproject.toml``) and the ``scripts`` folder the tools live in.

Found from this file's location, not the working directory, so ``python scripts/dev.py ...`` works from
anywhere inside or outside the repository.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["DEVKIT", "SCRIPTS", "ROOT", "PYPROJECT", "find_root", "shown"]


def find_root(start: Path) -> Path:
    """The first of ``start`` and its parents that holds a ``pyproject.toml``.

    Raises ``FileNotFoundError`` when none does (the devkit was copied outside a project).
    """
    for folder in (start, *start.parents):
        if (folder / "pyproject.toml").is_file():
            return folder
    raise FileNotFoundError(f"no pyproject.toml in {start} or any folder above it")


#: This package (``scripts/devkit``)
DEVKIT = Path(__file__).resolve().parent
#: The folder of ``dev.py`` and the project's own tools (``scripts``)
SCRIPTS = DEVKIT.parent
#: The repository root
ROOT = find_root(SCRIPTS)
PYPROJECT = ROOT / "pyproject.toml"


def shown(path: Path) -> Path:
    """``path`` relative to the repository root when it lies inside it (for messages)."""
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
