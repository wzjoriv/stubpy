"""
Version blocks in the body of a live class: the taken branch from the live class, the others from the source.
"""
from __future__ import annotations

from stubpy.analysis.harvest.models import ClassInfo, on_taken_path
from stubpy.state.context import StubContext

from ._ast_branches import branch_groups, branch_lines
from .ast_only import attribute_lines, emit_class_from_ast, emit_method_from_ast, keeps_method, member_text
from .branches import Unit
from .methods import generate_method_stub


def branched_names(info: ClassInfo | None) -> set[str]:
    """Return the names of the class members that sit in version branches."""
    if info is None:
        return set()
    return {m.name for kind in (info.attributes, info.methods, info.classes) for m in kind if m.branch}


def _live_text(cls: type, group: ClassInfo, info: ClassInfo, ctx: StubContext) -> str:
    """Return the stubs of the taken branch's members, methods introspected on *cls*."""
    lines = attribute_lines(group, ctx, "")
    lines += [emit_class_from_ast(c, ctx, "") for c in group.classes
              if not c.hint_ignore and (ctx.config.include_private or not c.name.startswith("_"))]
    methods: list[str] = []
    for name in dict.fromkeys(m.name for m in group.methods if not m.hint_ignore and keeps_method(m.name, ctx)):
        variants = [m for m in group.methods if m.name == name and m.is_overload]
        stub = "" if variants else generate_method_stub(cls, name, ctx, indent="", class_info=info)
        if stub:
            methods.extend(stub.split("\n"))
            continue
        for minfo in variants or [m for m in group.methods if m.name == name]:
            methods.extend(emit_method_from_ast(minfo, ctx, ""))
    return "\n".join(lines + ([""] if lines and methods else []) + methods)


def live_branch_lines(cls: type, info: ClassInfo | None, ctx: StubContext) -> list[str]:
    """Return the indented version blocks of a live class's body; ``[]`` when it has none."""
    if info is None:
        return []
    units = [
        Unit(_live_text(cls, group, info, ctx) if on_taken_path(path) else member_text(group, ctx), False, path)
        for path, group in branch_groups(info)
    ]
    return branch_lines(units, "    ")
