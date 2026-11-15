"""Class stubs."""
from __future__ import annotations

import typing

from stubpy.core.context import StubContext
from stubpy.resolve import get_own_annotations

from .annotations import annotation_to_str
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


def _base_names(cls: type, ctx: StubContext) -> list[str]:
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
            bases.append(b.__name__)
    return bases


def generate_class_stub(cls: type, ctx: StubContext) -> str:
    """Generate the full stub block for a live class.

    TypedDicts, NamedTuples and dataclasses get dedicated handling;
    ``@type_check_only`` and ``@dataclass_transform`` are re-emitted, and
    generic bases keep their subscripts.

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

    is_dc = is_dataclass(cls)
    include_docs = getattr(ctx.config, "include_docstrings", False)

    lines: list[str] = []
    if is_type_check_only(cls):
        lines.append("@type_check_only")
    dct_dec = dataclass_transform_decorator(cls)
    if dct_dec:
        lines.append(dct_dec)
    if is_dc:
        lines.append("@dataclass")

    bases = _base_names(cls, ctx)
    base_str = f"({', '.join(bases)})" if bases else ""
    lines.append(f"class {cls.__name__}{base_str}:")

    own_annotations: dict = get_own_annotations(cls)
    if is_dc:
        emit_dataclass_annotations(own_annotations, ctx, lines)
    else:
        for attr_name, ann in own_annotations.items():
            lines.append(f"    {attr_name}: {annotation_to_str(ann, ctx)}")

    if own_annotations:
        lines.append("")

    method_names = methods_defined_on(cls)
    if is_enum(cls):
        method_names = public_enum_methods(method_names)

    method_stubs: list[str] = []
    if is_dc:
        init_stub = synthesize_dataclass_init(cls, ctx)
        if init_stub:
            method_stubs.append(init_stub)
        method_names = [m for m in method_names if m != "__init__"]
    for mn in method_names:
        stub = generate_method_stub(cls, mn, ctx)
        if stub:
            method_stubs.append(stub)

    if include_docs:
        cls_doc_body = make_docstring_body(cls, "    ")
        if cls_doc_body != "...":
            lines.append(f"    {cls_doc_body}")

    if not method_stubs and not own_annotations and not include_docs:
        lines.append("    ...")
    elif not method_stubs and not own_annotations:
        if not getattr(cls, "__doc__", None) or not cls.__doc__.strip():
            lines.append("    ...")
    else:
        lines.extend(method_stubs)

    return "\n".join(lines)
