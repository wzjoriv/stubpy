"""Class stubs."""
from __future__ import annotations

import textwrap
import typing

from stubpy._constants import DATACLASS_GENERATED_METHODS
from stubpy.analysis.harvest.models import ClassInfo
from stubpy.core.context import StubContext
from stubpy.resolve import get_own_annotations

from .annotations import annotation_to_str, render_default
from .ast_only import emit_method_from_ast
from .decorators import decorator_base_name, stub_decorators
from .docstrings import make_docstring_body
from .methods import generate_method_stub, methods_defined_on
from .special.dataclass import emit_dataclass_annotations, synthesize_dataclass_init
from .special.detect import (
    dataclass_transform_decorator,
    is_dataclass,
    is_enum,
    is_namedtuple,
    is_type_check_only,
    is_typeddict,
)
from .special.enum import public_enum_methods
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
    """Return the base-class strings, preferring ``__orig_bases__`` to keep subscripts."""
    orig_bases = getattr(cls, "__orig_bases__", None)
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
    """Return the AST metadata of *cls* (nested classes included) from the symbol table, if any."""
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


def _attribute_lines(cls: type, own_annotations: dict, ctx: StubContext) -> list[str]:
    """Return ``name: type`` lines for unannotated plain-valued class attributes, and ``__hash__ = None``."""
    lines: list[str] = []
    for name, value in cls.__dict__.items():
        if name == "__hash__" and value is None:
            lines.append("    __hash__: ClassVar[None]")
            continue
        if name in own_annotations or name.startswith("__"):
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


def _is_synthesized(cls: type, name: str) -> bool:
    """Return ``True`` when method *name* was generated at runtime rather than written in source."""
    fn = cls.__dict__.get(name)
    code = getattr(getattr(fn, "__func__", fn), "__code__", None)
    return code is None or code.co_filename.startswith("<")


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _method_names(cls: type, info: ClassInfo | None, is_dc: bool, ctx: StubContext) -> list[str]:
    """Return the methods to stub, dropping private ones, generated dataclass methods and enum internals."""
    names = [n for n in methods_defined_on(cls) if ctx.config.include_private or not _is_private(n)]
    source_names = {m.name for m in info.methods} if info is not None else None
    if is_dc:
        names = [
            n for n in names
            if n not in DATACLASS_GENERATED_METHODS
            or (source_names is not None and n in source_names)
            or (source_names is None and not _is_synthesized(cls, n))
        ]
    if is_enum(cls):
        names = [
            n for n in public_enum_methods(names)
            if (n in source_names if source_names is not None else _defined_by(cls, n))
        ]
    return names


def _defined_by(cls: type, name: str) -> bool:
    """Return ``True`` when ``cls.__dict__[name]`` was written in *cls*'s own module."""
    fn = cls.__dict__.get(name)
    fn = getattr(fn, "__func__", fn)
    return name not in ("__new__", "__init__") and getattr(fn, "__module__", None) == cls.__module__


def _nested_classes(cls: type) -> list[type]:
    """Return the classes defined in *cls*'s body."""
    prefix = f"{cls.__qualname__}."
    return [
        v for v in cls.__dict__.values()
        if isinstance(v, type) and getattr(v, "__qualname__", "") == prefix + v.__name__
    ]


def _public_nested(cls: type, ctx: StubContext) -> list[type]:
    return [c for c in _nested_classes(cls) if ctx.config.include_private or not _is_private(c.__name__)]


def _method_stubs(cls: type, info: ClassInfo | None, is_dc: bool, ctx: StubContext) -> list[str]:
    """Return the stubs of the nested classes and methods, overloads taken from the source."""
    stubs = [textwrap.indent(generate_class_stub(c, ctx), "    ") for c in _public_nested(cls, ctx)]
    overloads: dict[str, list] = {}
    for m in info.methods if info is not None else []:
        if m.is_overload:
            overloads.setdefault(m.name, []).append(m)

    method_names = _method_names(cls, info, is_dc, ctx)
    init_from_source = info is not None and any(m.name == "__init__" for m in info.methods)
    if is_dc and not init_from_source and getattr(cls, "__dataclass_params__", None) is not None:
        if cls.__dataclass_params__.init:  # type: ignore[attr-defined]
            stubs.append(synthesize_dataclass_init(cls, ctx))
        method_names = [m for m in method_names if m != "__init__"]
    for mn in method_names:
        if mn in overloads:
            stubs.append("\n".join(
                line for variant in overloads[mn] for line in emit_method_from_ast(variant, ctx)
            ))
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
    base_str = f"({', '.join(bases)})" if bases else ""
    lines.append(f"class {cls.__name__}{base_str}:")

    own_annotations: dict = get_own_annotations(cls)
    field_lines: list[str] = []
    if is_enum(cls):
        field_lines.extend(_enum_member_lines(cls, ctx))
    if is_dc:
        emit_dataclass_annotations(own_annotations, ctx, field_lines)
    else:
        for attr_name, ann in own_annotations.items():
            field_lines.append(f"    {attr_name}: {annotation_to_str(ann, ctx)}")
    if not is_enum(cls):
        field_lines.extend(_attribute_lines(cls, own_annotations, ctx))

    if include_docs:
        cls_doc_body = make_docstring_body(cls, "    ")
        if cls_doc_body != "...":
            lines.append(f"    {cls_doc_body}")

    lines.extend(field_lines)
    method_stubs = _method_stubs(cls, info, is_dc, ctx)
    if field_lines and method_stubs:
        lines.append("")
    lines.extend(method_stubs)

    if not field_lines and not method_stubs and not (include_docs and _has_doc(cls)):
        lines.append("    ...")
    return "\n".join(lines)


def _has_doc(cls: type) -> bool:
    doc = getattr(cls, "__doc__", None)
    return bool(doc and doc.strip())

