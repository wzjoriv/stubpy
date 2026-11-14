"""Formatting of a single parameter as stub text."""
from __future__ import annotations

import inspect
from typing import Any

from stubpy.core.context import StubContext

from .defaults import default_to_str
from .registry import annotation_to_str


def _raw_preserves_aliases(raw: str, ctx: StubContext) -> bool:
    """Return ``True`` if *raw* references a registered alias module (e.g. ``types.Color``)."""
    for module_alias in ctx.type_module_imports:
        if f"{module_alias}." in raw:
            return True
    return False


def format_param(
    param: inspect.Parameter,
    hints: dict[str, Any],
    ctx: StubContext,
    raw_ann_override: str | None = None,
    docstring_type: str | None = None,
    inferred_type: str | None = None,
) -> str:
    """Format *param* as ``name: Type = default`` (or ``*name`` / ``**name``).

    The annotation comes from *raw_ann_override* when it names an alias
    module, else from *hints*, else from ``param.annotation``.  Without one,
    *inferred_type* is used as a real annotation and *docstring_type* is
    appended as a ``# type:`` comment.

    Examples
    --------
    >>> p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ...                       annotation=int, default=0)
    >>> format_param(p, {}, StubContext())
    'x: int = 0'
    """
    name = param.name
    default_str = default_to_str(param.default, ctx)

    if raw_ann_override is not None and _raw_preserves_aliases(raw_ann_override, ctx):
        ann_str = raw_ann_override
        for module_alias, import_stmt in ctx.type_module_imports.items():
            if f"{module_alias}." in raw_ann_override:
                ctx.used_type_imports[module_alias] = import_stmt
    else:
        ann_str = annotation_to_str(hints.get(name, param.annotation), ctx)

    doc_comment = ""
    if not ann_str:
        if inferred_type:
            ann_str = inferred_type
        elif docstring_type:
            doc_comment = f"  # type: {docstring_type}"

    if param.kind == inspect.Parameter.VAR_POSITIONAL:
        return f"*{name}" + (f": {ann_str}" if ann_str else "") + doc_comment
    if param.kind == inspect.Parameter.VAR_KEYWORD:
        return f"**{name}" + (f": {ann_str}" if ann_str else "") + doc_comment

    result = name
    if ann_str:
        result += f": {ann_str}"
    if default_str:
        result += f" = {default_str}"
    return result + doc_comment
