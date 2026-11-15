"""Resolve a name a function binds with its own import statement."""
from __future__ import annotations

import importlib
from typing import Any

from stubpy.analysis.harvest.models import FunctionInfo, LocalImport


def _imported(spec: LocalImport, package: str) -> Any:
    dots = "." * spec.level
    if spec.attr is None:
        return importlib.import_module(spec.module)
    module = importlib.import_module(f"{dots}{spec.module}" if spec.module or not spec.level else dots, package)
    if hasattr(module, spec.attr):
        return getattr(module, spec.attr)
    sub = f"{spec.module}.{spec.attr}" if spec.module else spec.attr
    return importlib.import_module(f"{dots}{sub}", package)


def local_target(info: FunctionInfo | None, name: str, namespace: dict[str, Any]) -> Any:
    """Return the object *name* is bound to by an import inside *info*'s function, or ``None``."""
    spec = info.local_imports.get(name) if info is not None else None
    if spec is None:
        return None
    package = namespace.get("__package__") or str(namespace.get("__name__", "")).rpartition(".")[0]
    try:
        return _imported(spec, package)
    except (ImportError, ValueError, TypeError):
        return None
