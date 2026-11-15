"""Dataclass stubs: field annotations and a synthesised ``__init__``."""
from __future__ import annotations

import dataclasses as _dc
import inspect

from stubpy._constants import KW_ONLY, VAR_KW, VAR_POS
from stubpy.core.context import StubContext
from stubpy.emit.annotations import annotation_to_str, render_default
from stubpy.emit.annotations.params import unwrap_initvar
from stubpy.resolve import class_hints_of, get_own_annotations, signature_of


def _field_annotation(cls: type, fname: str) -> object:
    """Return the annotation of field *fname*, searching *cls*'s MRO; ``InitVar[T]`` gives ``T``."""
    ann: object = None
    for klass in cls.__mro__:
        hints = class_hints_of(klass)
        if hints and fname in hints:
            ann = hints[fname]
            break
        own = get_own_annotations(klass)
        if own and fname in own:
            ann = own[fname]
            break
    return unwrap_initvar(ann)


def _init_params(cls: type) -> list[inspect.Parameter]:
    """Return the generated ``__init__`` parameters without ``self``, falling back to the fields."""
    sig = signature_of(cls.__dict__.get("__init__"))
    if sig is not None:
        return list(sig.parameters.values())[1:]
    params: list[inspect.Parameter] = []
    for fname, f in cls.__dataclass_fields__.items():
        if f._field_type is _dc._FIELD_CLASSVAR or not f.init:  # type: ignore[attr-defined]
            continue
        default = f.default if f.default is not _dc.MISSING else (
            Ellipsis if f.default_factory is not _dc.MISSING else inspect.Parameter.empty  # type: ignore[misc]
        )
        params.append(inspect.Parameter(fname, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default))
    return params


def synthesize_dataclass_init(cls: type, ctx: StubContext, indent: str = "    ") -> str:
    """Build an ``__init__`` stub matching the dataclass's generated ``__init__``.

    Field order, keyword-only fields and ``InitVar`` pseudo-fields follow the
    real signature; ``default_factory`` fields and non-literal defaults
    show ``= ...``.
    """
    params: list[str] = ["self"]
    star_added = False
    for p in _init_params(cls):
        if p.kind in (VAR_POS, VAR_KW):
            continue
        if p.kind == KW_ONLY and not star_added:
            params.append("*")
            star_added = True
        type_ann = _field_annotation(cls, p.name)
        type_str = annotation_to_str(type_ann, ctx) if type_ann is not None else ""
        text = f"{p.name}: {type_str}" if type_str else p.name
        if p.default is not inspect.Parameter.empty:
            text += f" = {render_default(p.default, ctx)}"
        params.append(text)

    if len(params) - 1 <= 2:
        return f"{indent}def __init__({', '.join(params)}) -> None: ..."
    inner = indent + "    "
    joined = f",\n{inner}".join(params)
    return f"{indent}def __init__(\n{inner}{joined},\n{indent}) -> None: ..."


def _field_default(cls: type | None, name: str, ctx: StubContext) -> str:
    """Return ``" = value"`` for a dataclass field with a default (``...`` unless a plain literal), else ``""``."""
    fields = getattr(cls, "__dataclass_fields__", None) if cls is not None else None
    f = fields.get(name) if isinstance(fields, dict) else None
    if f is None:
        return ""
    if f.default is not _dc.MISSING:
        return f" = {render_default(f.default, ctx)}"
    if f.default_factory is not _dc.MISSING:  # type: ignore[misc]
        return " = ..."
    return ""


def emit_dataclass_annotations(
    own_annotations: dict,
    ctx: StubContext,
    lines: list[str],
    indent: str = "    ",
    cls: type | None = None,
) -> None:
    """Append one ``name: Type`` line per field to *lines*, with ``= default`` when the field has one."""
    for attr_name, ann in own_annotations.items():
        lines.append(f"{indent}{attr_name}: {annotation_to_str(ann, ctx)}{_field_default(cls, attr_name, ctx)}")
