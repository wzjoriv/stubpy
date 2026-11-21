"""
Named constants of configuration files.
"""
from __future__ import annotations

CONFIG_FILE_NAME = "stubpy.toml"

PYPROJECT_FILE_NAME = "pyproject.toml"

CONFIG_PATH_KEYS: frozenset[str] = frozenset({"targets", "output_dir", "cache_dir"})

DEFAULT_TARGET_PYTHON = "3.10"
