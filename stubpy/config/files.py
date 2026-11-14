"""Config file discovery (``stubpy.toml`` / ``[tool.stubpy]``) and loading."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._toml import parse_toml
from .options import EXECUTION_MODES, StubConfig


def find_config_file(search_dir: str | Path) -> Path | None:
    """Walk upward from *search_dir* looking for a stubpy config file.

    Each directory is checked for ``stubpy.toml`` first, then for a
    ``pyproject.toml`` that contains a ``[tool.stubpy]`` section.

    Parameters
    ----------
    search_dir : str or Path
        Directory to start searching from.

    Returns
    -------
    Path or None
        The first matching file, or ``None`` when none is found before the
        filesystem root.
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
    """Load a :class:`~stubpy.StubConfig` from the nearest config file.

    Parameters
    ----------
    search_dir : str or Path
        Directory to begin the upward search.

    Returns
    -------
    StubConfig
        The file's settings over the defaults, or a default config when no
        file is found.  Unknown keys are ignored.

    Examples
    --------
    >>> from stubpy import load_config
    >>> cfg = load_config(".")
    >>> cfg.union_style in ("modern", "legacy")
    True
    """
    cfg_path = find_config_file(search_dir)
    if cfg_path is None:
        return StubConfig()
    return config_from_dict(_read_toml_section(cfg_path))


def config_from_dict(raw: dict[str, Any]) -> StubConfig:
    """Build a :class:`StubConfig` from a raw ``[tool.stubpy]`` mapping."""
    kwargs: dict[str, Any] = {}

    for key in ("include_private", "include_docstrings", "respect_all", "verbose", "strict"):
        if key in raw:
            kwargs[key] = bool(raw[key])

    if "execution_mode" in raw:
        mode_str = str(raw["execution_mode"]).lower()
        if mode_str in EXECUTION_MODES:
            kwargs["execution_mode"] = EXECUTION_MODES[mode_str]

    if "union_style" in raw:
        style = str(raw["union_style"]).lower()
        if style in ("modern", "legacy"):
            kwargs["union_style"] = style

    if "alias_style" in raw:
        style = str(raw["alias_style"]).lower()
        if style in ("compatible", "pep695", "auto"):
            kwargs["alias_style"] = style

    if "output_dir" in raw:
        kwargs["output_dir"] = str(raw["output_dir"])

    if "exclude" in raw:
        excl = raw["exclude"]
        if isinstance(excl, list):
            kwargs["exclude"] = [str(e) for e in excl]

    for key in ("infer_types_from_docstrings", "infer_types"):
        if key in raw:
            kwargs["infer_types_from_docstrings"] = bool(raw[key])
            break

    if "incremental_update" in raw or "incremental" in raw:
        kwargs["incremental_update"] = bool(
            raw.get("incremental_update", raw.get("incremental", False))
        )

    for key in ("resolve_kwargs", "resolve_args"):
        if key in raw:
            kwargs[key] = bool(raw[key])

    return StubConfig(**kwargs)


def _has_tool_stubpy(pyproject_path: Path) -> bool:
    """Return ``True`` if *pyproject_path* has a ``[tool.stubpy]`` section."""
    try:
        data = parse_toml(pyproject_path)
        return isinstance(data.get("tool", {}).get("stubpy"), dict)
    except Exception:
        return False


def _read_toml_section(cfg_path: Path) -> dict[str, Any]:
    """Return the stubpy settings from *cfg_path*, or ``{}`` on error."""
    try:
        data = parse_toml(cfg_path)
    except Exception:
        return {}

    if cfg_path.name == "stubpy.toml":
        return data if isinstance(data, dict) else {}

    section = data.get("tool", {}).get("stubpy", {})
    return section if isinstance(section, dict) else {}
