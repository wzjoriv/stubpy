"""
Live ``attrs`` classes: one annotation line per field the class body leaves untyped.
"""
from __future__ import annotations

from stubpy.emit.annotations import annotation_to_str
from stubpy.state.context import StubContext


def attrs_field_lines(cls: type, declared: set[str], ctx: StubContext, indent: str = "    ") -> list[str]:
    """Return ``name: Type`` for the ``attrs`` fields of *cls* not in *declared*; ``Any`` when untyped."""
    lines: list[str] = []
    for field in getattr(cls, "__attrs_attrs__", ()):
        name = field.name
        if name in declared or (name.startswith("_") and not ctx.config.include_private):
            continue
        text = annotation_to_str(field.type, ctx) if field.type is not None else ""
        lines.append(f"{indent}{name}: {text or 'Any'}")
    return lines
