"""
Class-body lines for attributes the class body does not declare: ``self.x`` assignments, ``__slots__``, descriptors.
"""
from __future__ import annotations

from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.core.context import StubContext
from stubpy.resolve.static import ClassRef

from ._static import resolver_of
from .annotations.style import style_text


def _get_type(info: ClassInfo) -> str | None:
    """Return what ``__get__`` gives on an instance: the overload whose ``obj`` is not ``None``, else its return."""
    gets: list[FunctionInfo] = [m for m in info.methods if m.name == "__get__"]
    variants = [m for m in gets if m.is_overload] or gets
    for m in variants:
        obj = m.raw_params[1].annotation_str if len(m.raw_params) > 1 else None
        if obj not in ("None", "type[None]") and m.raw_return_annotation:
            return m.raw_return_annotation
    return None


def descriptor_types(info: ClassInfo, ctx: StubContext) -> dict[str, str]:
    """Map class attributes assigned a descriptor instance (``d = Desc()``) to the type ``Desc.__get__`` returns."""
    module, index = ctx.source_module, ctx.source_index
    if module is None or index is None:
        return {}
    names = resolver_of(index).names
    out: dict[str, str] = {}
    for attr in info.attributes:
        if attr.annotation_str is not None or not (attr.value_repr or "").endswith(")"):
            continue
        ref = names.expression(module, attr.value_repr.partition("(")[0], None)
        if isinstance(ref, ClassRef) and ref.module is module:
            found = _get_type(ref.info)
            if found is not None:
                out[attr.name] = found
    return out


def declared_names(lines: list[str], info: ClassInfo | None) -> set[str]:
    """Return the names *lines* declare plus the class's methods, nested classes and non-descriptor attributes."""
    names = {line.strip().split(":")[0].split("=")[0].strip() for line in lines}
    if info is not None:
        names |= {m.name for m in info.methods} | {c.name for c in info.classes}
    return names


def source_attribute_lines(info: ClassInfo | None, declared: set[str], ctx: StubContext,
                           indent: str = "    ") -> list[str]:
    """Return ``name: T`` lines for descriptors, typed instance attributes and ``__slots__`` not in *declared*."""
    if info is None:
        return []
    lines: list[str] = []
    seen = set(declared)

    def add(name: str, text: str) -> None:
        if name in seen or (name.startswith("_") and not ctx.config.include_private):
            return
        seen.add(name)
        lines.append(f"{indent}{name}: {style_text(text, ctx) or text}")

    for name, text in descriptor_types(info, ctx).items():
        add(name, text)
    for attr in info.instance_attributes:
        add(attr.name, attr.annotation_str or "Any")
    for name in info.slots:
        add(name, "Any")
    return lines
