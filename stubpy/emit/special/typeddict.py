"""TypedDict stubs."""
from __future__ import annotations

import typing

from stubpy.core.context import StubContext
from stubpy.emit.annotations import annotation_to_str
from stubpy.resolve import get_own_annotations


def emit_typeddict_stub(cls: type, ctx: StubContext) -> str:
    """Return ``class Name(TypedDict[, total=False]):`` with one line per field."""
    suffix = ", total=False" if not getattr(cls, "__total__", True) else ""
    lines = [f"class {cls.__name__}(TypedDict{suffix}):"]

    try:
        ann = typing.get_type_hints(cls)
    except Exception:
        ann = get_own_annotations(cls)
    if not ann:
        lines.append("    ...")
    else:
        for field_name, field_type in ann.items():
            lines.append(f"    {field_name}: {annotation_to_str(field_type, ctx)}")

    return "\n".join(lines)
