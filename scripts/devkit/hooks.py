"""Project hooks the general tools call: ``"module:attribute"`` names from ``[tool.devkit.*]``, importable
from ``scripts/`` (a project tool folder), resolved when the tool runs."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from .config import ConfigError

__all__ = ["hook", "hooks"]


def hook(spec: str, where: str) -> Callable[..., Any]:
    """The callable ``spec`` names (``"module:function"``); ``where`` names the table in errors."""
    module_name, sep, attr = spec.partition(":")
    if not sep or not module_name or not attr:
        raise ConfigError(f"[{where}] {spec!r} is not 'module:function'")
    try:
        fn = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise ConfigError(f"[{where}] cannot load {spec!r}: {exc}") from exc
    if not callable(fn):
        raise ConfigError(f"[{where}] {spec!r} is not callable")
    return fn


def hooks(specs: list[str], where: str) -> list[tuple[str, Callable[..., Any]]]:
    """(name, callable) of each spec, in order."""
    return [(spec.partition(":")[2], hook(spec, where)) for spec in specs]
