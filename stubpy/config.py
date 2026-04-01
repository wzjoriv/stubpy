"""
stubpy.config
=============

Configuration file discovery and parsing.

stubpy looks for configuration in two places, in order:

1. A ``stubpy.toml`` file in the project root (or any parent directory).
2. A ``[tool.stubpy]`` section inside ``pyproject.toml``.

The first file found wins.  If neither exists the default
:class:`~stubpy.context.StubConfig` is returned unchanged.

Supported keys
--------------

.. code-block:: toml

    [tool.stubpy]
    include_private = false
    execution_mode  = "runtime"   # "runtime" | "ast_only" | "auto"
    output_dir      = "stubs"     # output directory for package processing
    exclude         = ["**/test_*.py", "setup.py"]
    typing_style    = "modern"    # "modern" (PEP 604) | "legacy" (Optional[])

All keys are optional.  Unknown keys are silently ignored so that future
versions can add new keys without breaking older configs.

Examples
--------
>>> from stubpy.config import load_config
>>> cfg = load_config(".")       # doctest: +SKIP
>>> cfg.typing_style
'modern'
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .context import ExecutionMode, StubConfig


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_config_file(search_dir: str | Path) -> Path | None:
    """Walk upward from *search_dir* looking for a stubpy config file.

    Checks each directory for (in order):

    1. ``stubpy.toml``
    2. ``pyproject.toml`` (only if it contains ``[tool.stubpy]``)

    Returns the first matching :class:`~pathlib.Path`, or ``None`` when
    no config is found before the filesystem root.

    Parameters
    ----------
    search_dir : str or Path
        Directory to start searching from (typically the package root or
        the source file's parent).

    Returns
    -------
    Path or None

    Examples
    --------
    >>> from stubpy.config import find_config_file
    >>> result = find_config_file(".")   # returns None if no config present
    """
    current = Path(search_dir).resolve()
    while True:
        stubpy_toml = current / "stubpy.toml"
        if stubpy_toml.exists():
            return stubpy_toml

        pyproject = current / "pyproject.toml"
        if pyproject.exists() and _has_tool_stubpy(pyproject):
            return pyproject

        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_config(search_dir: str | Path) -> StubConfig:
    """Load a :class:`~stubpy.context.StubConfig` from the nearest config file.

    Searches upward from *search_dir* for ``stubpy.toml`` or a
    ``[tool.stubpy]`` section in ``pyproject.toml``.  Returns a default
    :class:`~stubpy.context.StubConfig` when no config file is found.

    Parameters
    ----------
    search_dir : str or Path
        Directory to begin the upward search (typically the package being
        stubbed, or the current working directory).

    Returns
    -------
    StubConfig
        Fully populated config, falling back to defaults for any key not
        present in the file.

    Examples
    --------
    >>> from stubpy.config import load_config
    >>> cfg = load_config(".")
    >>> cfg.typing_style in ("modern", "legacy")
    True
    """
    cfg_path = find_config_file(search_dir)
    if cfg_path is None:
        return StubConfig()
    raw = _read_toml_section(cfg_path)
    return _build_config(raw)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _has_tool_stubpy(pyproject_path: Path) -> bool:
    """Return ``True`` if *pyproject_path* has a ``[tool.stubpy]`` section."""
    try:
        data = _parse_toml(pyproject_path)
        return isinstance(data.get("tool", {}).get("stubpy"), dict)
    except Exception:
        return False


def _read_toml_section(cfg_path: Path) -> dict[str, Any]:
    """Return the stubpy config dict from *cfg_path*, or ``{}`` on error."""
    try:
        data = _parse_toml(cfg_path)
    except Exception:
        return {}

    # stubpy.toml — the whole file is the config
    if cfg_path.name == "stubpy.toml":
        return data if isinstance(data, dict) else {}

    # pyproject.toml — extract [tool.stubpy]
    section = data.get("tool", {}).get("stubpy", {})
    return section if isinstance(section, dict) else {}


def _parse_toml(path: Path) -> dict[str, Any]:
    """Parse *path* as TOML and return the top-level mapping.

    Uses :mod:`tomllib` (Python 3.11+) or :mod:`tomli` (3.10 backport) if
    available; falls back to a minimal hand-rolled parser that covers the
    simple key = value / section syntax needed by stubpy.
    """
    # Python 3.11+ ships tomllib in the stdlib
    if sys.version_info >= (3, 11):
        import tomllib
        with open(path, "rb") as fh:
            return tomllib.load(fh)

    # Python 3.10 — try the tomli backport
    try:
        import tomli  # type: ignore[import]
        with open(path, "rb") as fh:
            return tomli.load(fh)
    except ImportError:
        pass

    # Minimal fallback parser (handles only the simple keys stubpy needs)
    return _minimal_toml_parse(path.read_text(encoding="utf-8"))


def _minimal_toml_parse(text: str) -> dict[str, Any]:
    """Parse a small subset of TOML sufficient for stubpy's own config keys.

    Supports:
    - Section headers: ``[section]``, ``[tool.stubpy]``
    - String values: ``key = "value"``
    - Boolean values: ``key = true`` / ``key = false``
    - Inline string arrays: ``key = ["a", "b"]``

    Anything not matched is silently skipped.
    """
    import re

    result: dict[str, Any] = {}
    current_path: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Section header
        m = re.match(r"^\[([^\]]+)\]$", line)
        if m:
            current_path = [p.strip() for p in m.group(1).split(".")]
            # Ensure the path exists in result
            node = result
            for part in current_path:
                node = node.setdefault(part, {})
            continue

        # Key = value
        m = re.match(r'^(\w+)\s*=\s*(.+)$', line)
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2).strip()

        # Decode value
        value: Any
        if raw_val in ("true", "True"):
            value = True
        elif raw_val in ("false", "False"):
            value = False
        elif raw_val.startswith('"') and raw_val.endswith('"'):
            value = raw_val[1:-1]
        elif raw_val.startswith("'") and raw_val.endswith("'"):
            value = raw_val[1:-1]
        elif raw_val.startswith("[") and raw_val.endswith("]"):
            # Inline array of strings
            inner = raw_val[1:-1]
            items = re.findall(r'["\']([^"\']*)["\']', inner)
            value = items
        else:
            continue  # skip unsupported value types

        # Insert at the right nesting level
        node = result
        for part in current_path:
            node = node.setdefault(part, {})
        node[key] = value

    return result


_EXECUTION_MODE_MAP: dict[str, ExecutionMode] = {
    "runtime":  ExecutionMode.RUNTIME,
    "ast_only": ExecutionMode.AST_ONLY,
    "auto":     ExecutionMode.AUTO,
}


def _build_config(raw: dict[str, Any]) -> StubConfig:
    """Convert a raw TOML dict into a :class:`~stubpy.context.StubConfig`."""
    kwargs: dict[str, Any] = {}

    if "include_private" in raw:
        kwargs["include_private"] = bool(raw["include_private"])

    if "respect_all" in raw:
        kwargs["respect_all"] = bool(raw["respect_all"])

    if "verbose" in raw:
        kwargs["verbose"] = bool(raw["verbose"])

    if "strict" in raw:
        kwargs["strict"] = bool(raw["strict"])

    if "execution_mode" in raw:
        mode_str = str(raw["execution_mode"]).lower()
        if mode_str in _EXECUTION_MODE_MAP:
            kwargs["execution_mode"] = _EXECUTION_MODE_MAP[mode_str]

    if "typing_style" in raw:
        style = str(raw["typing_style"]).lower()
        if style in ("modern", "legacy"):
            kwargs["typing_style"] = style

    if "output_dir" in raw:
        kwargs["output_dir"] = str(raw["output_dir"])

    if "exclude" in raw:
        excl = raw["exclude"]
        if isinstance(excl, list):
            kwargs["exclude"] = [str(e) for e in excl]

    return StubConfig(**kwargs)
