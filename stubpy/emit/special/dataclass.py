"""Dataclass stubs: field annotations and a synthesised ``__init__``."""
from __future__ import annotations

import dataclasses as _dc
import typing

from stubpy.core.context import StubContext
from stubpy.emit.annotations import annotation_to_str
from stubpy.resolve import get_own_annotations


def _field_annotation(cls: type, fname: str) -> object:
    """Return the annotation of field *fname*, searching *cls*'s MRO."""
    for klass in cls.__mro__:
        try:
            hints = typing.get_type_hints(klass)
            if fname in hints:
                return hints[fname]
        except Exception:
            pass
        ann = get_own_annotations(klass)
        if ann and fname in ann:
            return ann[fname]
    return None


def synthesize_dataclass_init(cls: type, ctx: StubContext, indent: str = "    ") -> str:
    """Build an ``__init__`` stub from ``__dataclass_fields__``.

    ``ClassVar`` and ``init=False`` fields are skipped; ``default_factory``
    fields show ``= ...``.
    """
    params: list[str] = ["self"]
    for fname, f in cls.__dataclass_fields__.items():
        if f._field_type is _dc._FIELD_CLASSVAR:  # type: ignore[attr-defined]
            continue
        if not f.init:
            continue

        type_ann = _field_annotation(cls, fname)
        type_str = annotation_to_str(type_ann, ctx) if type_ann is not None else ""

        if f.default is not _dc.MISSING:
            p = (f"{fname}: {type_str} = {repr(f.default)}"
                 if type_str else f"{fname} = {repr(f.default)}")
        elif f.default_factory is not _dc.MISSING:  # type: ignore[misc]
            p = f"{fname}: {type_str} = ..." if type_str else f"{fname} = ..."
        else:
            p = f"{fname}: {type_str}" if type_str else fname
        params.append(p)

    if len(params) - 1 <= 2:
        return f"{indent}def __init__({', '.join(params)}) -> None: ..."
    inner = indent + "    "
    joined = f",\n{inner}".join(params)
    return f"{indent}def __init__(\n{inner}{joined},\n{indent}) -> None: ..."


def emit_dataclass_annotations(
    own_annotations: dict,
    ctx: StubContext,
    lines: list[str],
    indent: str = "    ",
) -> None:
    """Append one ``name: Type`` line per field to *lines*."""
    for attr_name, ann in own_annotations.items():
        lines.append(f"{indent}{attr_name}: {annotation_to_str(ann, ctx)}")
