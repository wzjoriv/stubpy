"""
Class-body lines for attributes the class body does not declare: ``self.x`` assignments, ``__slots__``, descriptors.
"""
from __future__ import annotations

import ast

from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.core.context import StubContext
from stubpy.resolve.static import ClassRef, SourceModule, static_mro

from ._static import bind_names, names_in, resolver_of
from .annotations.private_aliases import inline_private_aliases
from .annotations.style import style_text

_GENERIC_BASES: frozenset[str] = frozenset({"Generic", "Protocol", "typing.Generic", "typing.Protocol"})


def _get_type(info: ClassInfo) -> str | None:
    """Return what ``__get__`` gives on an instance: the overload whose ``obj`` is not ``None``, else its return."""
    gets: list[FunctionInfo] = [m for m in info.methods if m.name == "__get__"]
    variants = [m for m in gets if m.is_overload] or gets
    for m in variants:
        obj = m.raw_params[1].annotation_str if len(m.raw_params) > 1 else None
        if obj not in ("None", "type[None]") and m.raw_return_annotation:
            return m.raw_return_annotation
    return None


def _type_params(ref: ClassRef) -> list[str]:
    """Return the type parameters of a generic class, from ``Generic[...]`` or PEP 695 brackets."""
    for base in ref.info.bases:
        head, _, rest = base.partition("[")
        if head.strip() in _GENERIC_BASES and rest:
            return [p.strip().lstrip("*") for p in rest.rstrip("]").split(",")]
    return [p.split(":")[0].split("=")[0].strip().lstrip("*") for p in ref.info.type_params]


def _substitute(text: str, mapping: dict[str, str]) -> str | None:
    """Replace the names in *mapping* inside the type expression *text*."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None

    class _Swap(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:
            return ast.parse(mapping[node.id], mode="eval").body if node.id in mapping else node

    return ast.unparse(_Swap().visit(tree))


def _descriptor_type(module: SourceModule, value: str, ctx: StubContext) -> str | None:
    """Return the instance type of ``Desc(...)`` / ``Desc[T](...)``, with type arguments substituted."""
    try:
        node = ast.parse(value, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Call):
        return None
    func, args = node.func, []
    if isinstance(func, ast.Subscript):
        args = [ast.unparse(e) for e in (func.slice.elts if isinstance(func.slice, ast.Tuple) else [func.slice])]
        func = func.value
    ref = resolver_of(ctx.source_index).names.expression(module, ast.unparse(func), None)
    if not isinstance(ref, ClassRef):
        return None
    found = _get_type(ref.info)
    if found is None:
        return None
    params = _type_params(ref)
    mapping = {p: (args[i] if i < len(args) else "Any") for i, p in enumerate(params)}
    found = _substitute(found, mapping) if mapping else found
    if found is None or ref.module is module:
        return found
    names = [n for n in names_in(found) or [] if n not in names_in(" | ".join(args) or "None")]
    return found if bind_names(names, ref.module, ctx) else None


def descriptor_types(info: ClassInfo, ctx: StubContext) -> dict[str, str]:
    """Map class attributes assigned a descriptor instance (``d = Desc()``) to the type ``Desc.__get__`` returns."""
    module, index = ctx.source_module, ctx.source_index
    if module is None or index is None:
        return {}
    out: dict[str, str] = {}
    for attr in info.attributes:
        if attr.annotation_str is not None or not (attr.value_repr or "").endswith(")"):
            continue
        found = _descriptor_type(module, attr.value_repr, ctx)
        if found is not None:
            out[attr.name] = found
    return out


def _inherited_names(info: ClassInfo, ctx: StubContext) -> set[str]:
    """Return the members the known ancestors of *info* declare."""
    module, index = ctx.source_module, ctx.source_index
    if module is None or index is None:
        return set()
    names: set[str] = set()
    for klass in static_mro(resolver_of(index).names, ClassRef(module, info))[1:]:
        if isinstance(klass, ClassRef):
            ki = klass.info
            names |= {m.name for m in ki.methods} | {a.name for a in ki.attributes}
            names |= {a.name for a in ki.instance_attributes} | set(ki.slots)
    return names


def declared_names(lines: list[str], info: ClassInfo | None) -> set[str]:
    """Return the names *lines* declare plus the class's methods, nested classes and non-descriptor attributes."""
    names = {line.strip().split(":")[0].split("=")[0].strip() for line in lines}
    if info is not None:
        names |= {m.name for m in info.methods} | {c.name for c in info.classes}
    return names


def source_attribute_lines(info: ClassInfo | None, declared: set[str], ctx: StubContext,
                           indent: str = "    ") -> list[str]:
    """Return ``name: T`` lines for descriptors, instance attributes and ``__slots__`` not in *declared*.

    An instance attribute whose type is unknown is typed ``Any``, unless an ancestor already declares it.
    """
    if info is None:
        return []
    lines: list[str] = []
    seen = set(declared)

    def add(name: str, text: str) -> None:
        if name in seen or (name.startswith("_") and not ctx.config.include_private):
            return
        seen.add(name)
        text = inline_private_aliases(text, ctx.module_namespace, ctx)
        lines.append(f"{indent}{name}: {style_text(text, ctx) or text}")

    for name, text in descriptor_types(info, ctx).items():
        add(name, text)
    untyped = [a for a in info.instance_attributes if a.annotation_str is None]
    inherited = (_inherited_names(info, ctx) | {a.name for a in info.attributes}) if untyped else set()
    for attr in info.instance_attributes:
        if attr.annotation_str is not None or attr.name not in inherited:
            add(attr.name, attr.annotation_str or "Any")
    for name in info.slots:
        add(name, "Any")
    return lines
