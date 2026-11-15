"""Config file discovery (``stubpy.toml`` / ``[tool.stubpy]``) and loading."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from stubpy._constants import CONFIG_FILE_NAME, CONFIG_PATH_KEYS, PYPROJECT_FILE_NAME

from ._toml import parse_toml
from .options import Config


def find_config_file(start: str | os.PathLike[str] = ".") -> Path | None:
    """Return the nearest ``stubpy.toml`` or ``pyproject.toml`` with ``[tool.stubpy]`` at or above *start*.

    In each folder ``stubpy.toml`` wins over ``pyproject.toml``.  A file
    path starts the search in its folder.
    """
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for folder in (current, *current.parents):
        stubpy_toml = folder / CONFIG_FILE_NAME
        if stubpy_toml.is_file():
            return stubpy_toml
        pyproject = folder / PYPROJECT_FILE_NAME
        if pyproject.is_file() and _stubpy_table(pyproject) is not None:
            return pyproject
    return None


def load_config(start: str | os.PathLike[str] = ".") -> Config:
    """Load the nearest stubpy configuration.

    Searches *start* and every folder above it for ``stubpy.toml`` (the whole
    file is the configuration; a file holding only a ``[tool.stubpy]`` table
    is read the same way) or a ``pyproject.toml`` with a ``[tool.stubpy]``
    table.  Relative ``targets`` and ``output_dir`` are
    resolved against the folder holding the file, so the result does not
    depend on the working directory.

    Parameters
    ----------
    start : str or os.PathLike, default "."
        Folder (or file) to start the upward search from.

    Returns
    -------
    Config
        The file's options over the defaults, or ``Config()`` when no file
        is found.

    Raises
    ------
    ValueError
        If the file has an unknown key or an invalid value, or is not valid TOML.

    Examples
    --------
    ``pyproject.toml``::

        [tool.stubpy]
        targets = ["src/mypkg"]
        modules = ["mypkg._native"]
        output_dir = "stubs"
        mode = "auto"

    >>> import stubpy
    >>> cfg = stubpy.load_config()  # doctest: +SKIP
    >>> stubpy.generate(config=cfg)  # doctest: +SKIP
    """
    path = find_config_file(start)
    if path is None:
        return Config()
    try:
        raw = _read_table(path)
        return Config.from_dict(_resolve_paths(raw, path.parent))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _resolve_paths(raw: dict[str, Any], base: Path) -> dict[str, Any]:
    """Return *raw* with relative ``targets`` / ``output_dir`` joined onto *base*."""
    out = dict(raw)
    for key in CONFIG_PATH_KEYS:
        value = out.get(key)
        if isinstance(value, str):
            out[key] = _join(base, value) if key == "output_dir" else [_join(base, value)]
        elif isinstance(value, list):
            out[key] = [_join(base, v) if isinstance(v, str) else v for v in value]
    return out


def _join(base: Path, value: str) -> str:
    return value if Path(value).is_absolute() else str(base / value)


def _stubpy_table(pyproject: Path) -> dict[str, Any] | None:
    """Return the ``[tool.stubpy]`` table of *pyproject*, or ``None``."""
    try:
        data = parse_toml(pyproject)
    except Exception:
        return None
    table = data.get("tool", {}).get("stubpy")
    return table if isinstance(table, dict) else None


def _read_table(path: Path) -> dict[str, Any]:
    """Return the stubpy options stored in *path*."""
    if path.name == CONFIG_FILE_NAME:
        try:
            data = parse_toml(path)
        except Exception as exc:
            raise ValueError(f"not valid TOML: {exc}") from exc
        if not isinstance(data, dict):
            return {}
        nested = data.get("tool", {}).get("stubpy") if isinstance(data.get("tool"), dict) else None
        if isinstance(nested, dict) and set(data) == {"tool"}:
            return nested
        return data
    return _stubpy_table(path) or {}
