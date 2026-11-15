"""The devkit's settings: the ``[tool.devkit]`` table of the repository's ``pyproject.toml``.

Every key is optional. A general tool whose table is missing (``[tool.devkit.pyi]``, ``[tool.devkit.tiers]``,
``[tool.devkit.bench]``, ...) is off: ``dev.py`` does not offer it. ``tools`` lists the project's own tools as
``"module:attribute"`` (a ``typer.Typer`` or a function) importable from ``scripts/``.
"""

from __future__ import annotations

import functools
import sys
from typing import Any

from .paths import PYPROJECT, ROOT

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    try:
        import tomli as tomllib
    except ImportError as exc:  # the dev extra installs it
        raise ImportError("the devkit needs tomli on Python < 3.11: pip install tomli") from exc

__all__ = ["ConfigError", "pyproject", "project_name", "settings", "section", "typed", "root_path"]


class ConfigError(ValueError):
    """A ``[tool.devkit]`` value has the wrong shape."""


@functools.cache
def pyproject() -> dict[str, Any]:
    """The repository's whole ``pyproject.toml``."""
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


def project_name() -> str:
    """``[project] name``, else the repository folder's name."""
    return str(pyproject().get("project", {}).get("name") or ROOT.name)


def settings() -> dict[str, Any]:
    """The whole ``[tool.devkit]`` table (empty when the project has none)."""
    table = pyproject().get("tool", {}).get("devkit", {})
    if not isinstance(table, dict):
        raise ConfigError(f"{PYPROJECT}: [tool.devkit] must be a table")
    return table


def section(name: str) -> dict[str, Any] | None:
    """``[tool.devkit.<name>]``, or ``None`` when the project leaves that tool off."""
    value = settings().get(name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"{PYPROJECT}: [tool.devkit.{name}] must be a table")
    return value


def typed(table: dict[str, Any], key: str, kind: type | tuple[type, ...], default: Any, where: str) -> Any:
    """``table[key]`` checked to be a ``kind`` (``default`` when absent); ``where`` names the table in errors."""
    value = table.get(key, default)
    if value is not default and not isinstance(value, kind):
        names = kind.__name__ if isinstance(kind, type) else " or ".join(k.__name__ for k in kind)
        raise ConfigError(f"{PYPROJECT}: [{where}] {key} must be a {names}, not {value!r}")
    return value


def root_path(path: str) -> str:
    """``path`` from the config (relative to the repository root unless absolute) as an absolute path."""
    return str((ROOT / path).resolve())
