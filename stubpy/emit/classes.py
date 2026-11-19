"""
Class stubs.
"""
from __future__ import annotations

import sys
import textwrap
import typing
from typing import Any

from stubpy.analysis.harvest.models import ClassInfo
from stubpy.analysis.hints import is_ignored
from stubpy.core.context import StubContext
from stubpy.resolve import get_own_annotations

from ._class_branches import branched_names, live_branch_lines
from ._instance_attrs import declared_names, source_attribute_lines
from ._members import public_nested, stub_method_names
from .annotations import annotation_to_str, render_default
from .annotations.source import aliased_text
from .ast_only import emit_method_from_ast
from .decorators import decorator_base_name, stub_decorators
from .docstrings import make_docstring_body
from .methods import generate_method_stub
from .signature import generic_name, unique
from .special.dataclass import emit_dataclass_annotations, synthesize_dataclass_init
from .special.detect import (
    dataclass_transform_decorator,
    is_dataclass,
    is_enum,
    is_namedtuple,
    is_type_check_only,
    is_typeddict,
)
from .special.namedtuple import generate_namedtuple_stub
from .special.typeddict import emit_typeddict_stub

_PLAIN_VALUE_TYPES: tuple[type, ...] = (int, float, complex, str, bytes, bool, list, dict, tuple, set, frozenset)
_AST_ONLY_CLASS_DECORATORS: frozenset[str] = frozenset({"final", "runtime_checkable", "deprecated"})


def _metaclass_keyword(cls: type, ctx: StubContext) -> list[str]:
    """Return ``["metaclass=M"]`` when *cls* declares a metaclass its bases do not already have."""
    meta = type(cls)
    if meta is type or any(isinstance(b, meta) for b in cls.__bases__ if b is not object):
        return []
    if is_enum(cls) or is_typeddict(cls) or is_namedtuple(cls):
        return []
    return [f"metaclass={annotation_to_str(meta, ctx)}"]


def _base_names(cls: type, ctx: StubContext) -> list[str]:
    """Return the base-class strings (and a metaclass keyword), keeping generic subscripts."""
    return _plain_base_names(cls, ctx) + _metaclass_keyword(cls, ctx)


def _plain_base_names(cls: type, ctx: StubContext) -> list[str]:
    """Return the base-class strings, preferring the class's own ``__orig_bases__`` to keep subscripts."""
    orig_bases = cls.__dict__.get("__orig_bases__")
    bases: list[str] = []
    if orig_bases:
        typed_dict = getattr(typing, "TypedDict", None)
        for b in orig_bases:
            if b is object:
                continue
            if b is typed_dict:
                bases.append("TypedDict")
                continue
            b_str = annotation_to_str(b, ctx)
            if b_str and b_str not in ("object", ""):
                bases.append(b_str)
        return bases
    for b in cls.__bases__:
        if b is object:
            continue
        if b is tuple and is_namedtuple(cls):
            bases.append("NamedTuple")
        else:
            bases.append(annotation_to_str(b, ctx))
    return bases


def class_ast_info(cls: type, ctx: StubContext) -> ClassInfo | None:
    """Return the AST metadata of a class, nested classes included.

    Parameters
    ----------
    cls : type
        The class; its ``__qualname__`` is walked through nested classes.
    ctx : StubContext
        The current run context.

    Returns
    -------
    ClassInfo or None
        The class's info from the symbol table, or ``None`` when there is none.

    Examples
    --------
    >>> class Point: ...
    >>> class_ast_info(Point, StubContext()) is None
    True
    """
    table = ctx.symbol_table
    if table is None:
        return None
    parts = getattr(cls, "__qualname__", cls.__name__).split(".")
    sym = table.get_class(parts[0])
    info = sym.ast_info if sym is not None else None
    for part in parts[1:]:
        if info is None:
            return None
        info = next((c for c in info.classes if c.name == part), None)
    return info


def _class_decorators(cls: type, info: ClassInfo | None, ctx: StubContext) -> list[str]:
    """Return the decorator lines of a live class: runtime-detected ones plus allowed source ones."""
    source = stub_decorators(info.decorators) if info is not None else []
    lines: list[str] = []
    if is_type_check_only(cls):
        lines.append("@type_check_only")
    dct_dec = dataclass_transform_decorator(cls, ctx)
    if dct_dec:
        lines.append(dct_dec)
    if is_dataclass(cls):
        lines.append("@" + next((d for d in source if decorator_base_name(d) == "dataclass"), "dataclass"))
    for dec in source:
        if decorator_base_name(dec) in _AST_ONLY_CLASS_DECORATORS and f"@{dec}" not in lines:
            lines.append(f"@{dec}")
    return lines


def _annotated_in_bases(cls: type, name: str) -> bool:
    return any(name in get_own_annotations(base) for base in cls.__mro__[1:])


def _attribute_annotation(cls: type, name: str, ann: Any, info: ClassInfo | None, ctx: StubContext) -> str:
    """Render a class attribute's annotation, keeping the alias names the source wrote."""
    raw = next((a.annotation_str for a in info.attributes if a.name == name), None) if info is not None else None
    if cls.__module__ == ctx.module_name:
        namespace = ctx.module_namespace
    else:
        namespace = getattr(sys.modules.get(cls.__module__), "__dict__", None)
    text = aliased_text(raw, namespace, ctx) if isinstance(namespace, dict) and ctx.module_namespace else None
    return text or annotation_to_str(ann, ctx)


def _attribute_lines(cls: type, own_annotations: dict, ctx: StubContext, info: ClassInfo | None,
                     skip: set[str]) -> list[str]:
    """Return ``name: type`` lines for unannotated plain-valued class attributes, and ``__hash__ = None``.

    A dataclass's ``__hash__ = None`` is only kept when the source wrote it.
    """
    lines: list[str] = []
    for name, value in cls.__dict__.items():
        if name == "__hash__" and value is None:
            if not is_dataclass(cls) or (info is not None and any(a.name == "__hash__" for a in info.attributes)):
                lines.append("    __hash__: ClassVar[None]")
            continue
        if name in own_annotations or name in skip or name.startswith("__"):
            continue
        if name.startswith("_") and not ctx.config.include_private:
            continue
        if type(value) not in _PLAIN_VALUE_TYPES or _annotated_in_bases(cls, name):
            continue
        lines.append(f"    {name}: {type(value).__name__}")
    return lines


def _enum_member_lines(cls: type, ctx: StubContext) -> list[str]:
    """Return ``NAME = value`` per enum member and ``ALIAS = NAME`` per alias."""
    lines: list[str] = []
    for name, member in cls.__members__.items():
        if member.name != name and isinstance(member.name, str):
            lines.append(f"    {name} = {member.name}")
        else:
            lines.append(f"    {name} = {render_default(member._value_, ctx)}")
    return lines


def _method_stubs(cls: type, info: ClassInfo | None, is_dc: bool, ctx: StubContext, skip: set[str]) -> list[str]:
    """Return the stubs of the nested classes and methods, overloads taken from the source; *skip* names are left out."""
    stubs = [
        textwrap.indent(generate_class_stub(c, ctx), "    ") for c in public_nested(cls, info, ctx)
        if c.__name__ not in skip
    ]
    overloads: dict[str, list] = {}
    for m in info.methods if info is not None else []:
        if m.is_overload:
            overloads.setdefault(m.name, []).append(m)

    method_names = [n for n in stub_method_names(cls, info, is_dc, ctx) if n not in skip]
    init_from_source = info is not None and any(m.name == "__init__" for m in info.methods)
    if is_dc and not init_from_source and getattr(cls, "__dataclass_params__", None) is not None:
        if cls.__dataclass_params__.init:  # type: ignore[attr-defined]
            stubs.append(synthesize_dataclass_init(cls, ctx))
        method_names = [m for m in method_names if m != "__init__"]
    for mn in method_names:
        if mn in overloads:
            if is_ignored(cls.__dict__.get(mn)) or any(v.hint_ignore for v in overloads[mn]):
                continue
            variants = unique([tuple(emit_method_from_ast(variant, ctx)) for variant in overloads[mn]])
            stubs.append("\n".join(line for variant in variants for line in variant))
            continue
        stub = generate_method_stub(cls, mn, ctx, class_info=info)
        if stub:
            stubs.append(stub)
    return stubs


def generate_class_stub(cls: type, ctx: StubContext) -> str:
    """Generate the full stub block for a live class.

    TypedDicts, NamedTuples and dataclasses get dedicated handling; enum
    members are listed; stub-relevant decorators are re-emitted; generic
    bases keep their subscripts; nested classes are emitted in place.

    Parameters
    ----------
    cls : type
        The class to stub.
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        The class stub, without a trailing newline.

    Examples
    --------
    >>> class Point:
    ...     x: float
    ...     def __init__(self, x: float) -> None: ...
    >>> print(generate_class_stub(Point, StubContext()))
    class Point:
        x: float
    <BLANKLINE>
        def __init__(self, x: float) -> None: ...
    """
    if is_typeddict(cls):
        return emit_typeddict_stub(cls, ctx)
    if is_namedtuple(cls):
        return generate_namedtuple_stub(cls, ctx)

    info = class_ast_info(cls, ctx)
    is_dc = is_dataclass(cls)
    include_docs = getattr(ctx.config, "include_docstrings", False)

    lines = _class_decorators(cls, info, ctx)
    bases = _base_names(cls, ctx)
    if info is not None and info.type_params:
        bases = [b for b in bases if not b.startswith("Generic[")]
    base_str = f"({', '.join(bases)})" if bases else ""
    lines.append(f"class {generic_name(cls.__name__, info)}{base_str}:")

    own_annotations: dict = get_own_annotations(cls)
    skip = branched_names(info)
    field_lines: list[str] = []
    if is_enum(cls):
        field_lines.extend(_enum_member_lines(cls, ctx))
    if is_dc:
        emit_dataclass_annotations(own_annotations, ctx, field_lines, cls=cls)
    else:
        for attr_name, ann in own_annotations.items():
            if attr_name in skip or (
                attr_name.startswith("_") and not attr_name.startswith("__") and not ctx.config.include_private
            ):
                continue
            field_lines.append(f"    {attr_name}: {_attribute_annotation(cls, attr_name, ann, info, ctx)}")
    if not is_enum(cls):
        field_lines.extend(_attribute_lines(cls, own_annotations, ctx, info, skip))
        field_lines.extend(source_attribute_lines(info, declared_names(field_lines, info) | set(own_annotations), ctx))

    if include_docs:
        cls_doc_body = make_docstring_body(cls, "    ")
        if cls_doc_body != "...":
            lines.append(f"    {cls_doc_body}")

    lines.extend(field_lines)
    method_stubs = _method_stubs(cls, info, is_dc, ctx, skip)
    if field_lines and method_stubs:
        lines.append("")
    lines.extend(method_stubs)
    blocks = live_branch_lines(cls, info, ctx)
    if blocks and (field_lines or method_stubs):
        lines.append("")
    lines.extend(blocks)

    if not field_lines and not method_stubs and not blocks and not (include_docs and _has_doc(cls)):
        lines.append("    ...")
    return "\n".join(lines)


def _has_doc(cls: type) -> bool:
    doc = getattr(cls, "__doc__", None)
    return bool(doc and doc.strip())

