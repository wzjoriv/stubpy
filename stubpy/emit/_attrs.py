"""
AST-only ``attrs`` classes: typed field lines and the synthesised ``__init__``.
"""
from __future__ import annotations

from stubpy.analysis.harvest.models import ClassInfo
from stubpy.resolve.static import ClassRef, attrs_fields, kind_of
from stubpy.state.context import StubContext

from ._def_layout import format_def
from ._static import bind_foreign, resolver_of
from .annotations import format_param
from .signature import render_params, with_separators


def _ref(ci: ClassInfo, ctx: StubContext) -> ClassRef | None:
    """The class as the static resolver sees it, or ``None`` for a class that is not an ``attrs`` class."""
    if ctx.source_module is None or ctx.source_index is None or kind_of(ci) != "attrs":
        return None
    return ClassRef(ctx.source_module, ci)


def attrs_field_lines(ci: ClassInfo, ctx: StubContext, indent: str, declared: set[str]) -> list[str]:
    """Return ``name: Type`` for the fields of an ``attrs`` class not already *declared*; ``Any`` when untyped."""
    cref = _ref(ci, ctx)
    if cref is None:
        return []
    lines = []
    for f in attrs_fields(cref):
        if f.name in declared or (f.name.startswith("_") and not ctx.config.include_private):
            continue
        lines.append(f"{indent}{f.name}: {f.type or 'Any'}")
    return lines


def attrs_init_lines(ci: ClassInfo, ctx: StubContext, indent: str) -> list[str]:
    """Return the ``__init__`` an ``attrs`` decorator synthesises, or ``[]`` when there is none to add."""
    cref = _ref(ci, ctx)
    if cref is None or any(m.name == "__init__" for m in ci.methods):
        return []
    params = resolver_of(ctx.source_index).constructor(cref)
    if params is None:
        return []
    bound = with_separators([bind_foreign(p, h, ctx) for p, h in params])
    param_strs = ["self"] + render_params(bound, lambda p, h: format_param(p, h, ctx))
    return format_def(indent, "def", "__init__", param_strs, " -> None", len(param_strs) - 1)
