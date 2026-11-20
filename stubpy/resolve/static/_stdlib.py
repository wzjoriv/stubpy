"""
Standard-library and builtin callees of source-only back-tracing: importing them is always safe.
"""
from __future__ import annotations

import builtins
import importlib
import sys
from typing import Any

from stubpy.analysis.harvest.models import FunctionInfo

from .._typed_stdlib import table_key, typed_stdlib_params
from ..callables import signature_of
from ..hints import get_hints_for_method
from .index import SourceModule


def _origin(module: SourceModule, name: str, caller: FunctionInfo | None) -> str | None:
    """The dotted path *name* comes from, through the module's (or the caller's local) imports, else builtins."""
    head, _, rest = name.partition(".")
    local = (caller.local_imports if caller is not None else {}).get(head)
    if local is not None and not local.level:
        base = f"{local.module}.{local.attr}" if local.attr else local.module
        return f"{base}.{rest}" if rest else base
    for imp in reversed(module.symbols.imports):
        if imp.local != head or (imp.module or "").startswith("."):
            continue
        base = f"{imp.module}.{imp.name}" if imp.module else (imp.name if imp.asname else head)
        return f"{base}.{rest}" if rest else base
    defined = {c.name for c in module.symbols.classes} | {f.name for f in module.symbols.functions} | {
        v.name for v in module.symbols.variables}
    if head not in defined and not head.startswith("_") and hasattr(builtins, head):
        return f"builtins.{name}"
    return None


def _resolve(dotted: str) -> Any:
    """Import the longest importable stdlib prefix of *dotted* and walk the rest; ``None`` when that fails."""
    parts = dotted.split(".")
    if parts[0] not in sys.stdlib_module_names and parts[0] != "builtins":
        return None
    for split in range(len(parts), 0, -1):
        try:
            obj: Any = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        try:
            for attr in parts[split:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return None
        return obj
    return None


def stdlib_params(module: SourceModule, name: str, caller: FunctionInfo | None) -> list | None:
    """The parameters of a standard-library or builtin callee *name*, from its live signature."""
    origin = _origin(module, name.removesuffix("()"), caller)
    tabled = typed_stdlib_params(table_key(origin)) if origin else None
    if tabled is not None:
        return tabled
    obj = _resolve(origin) if origin else None
    if obj is None or not callable(obj):
        return None
    owner = _resolve(origin.rpartition(".")[0]) if origin and "." in origin else None
    if isinstance(owner, type) and not isinstance(obj, type):
        from ..params import resolve_params

        home = vars(sys.modules[owner.__module__]) if owner.__module__ in sys.modules else None
        return resolve_params(owner, origin.rpartition(".")[2], namespace=home) or None
    globals_ = getattr(obj, "__globals__", None)
    if isinstance(globals_, dict):
        from ..params import resolve_function_params

        return resolve_function_params(obj, None, globals_)
    sig = signature_of(obj)
    if sig is None:
        return None
    hints = get_hints_for_method(obj)
    params = list(sig.parameters.values())
    if isinstance(obj, type) and params and params[0].name == "self":
        params = params[1:]
    return [(p, hints) for p in params]
