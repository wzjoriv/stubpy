"""
AST-only class-body attribute lines: enum members, annotated fields and typed literals.
"""
from __future__ import annotations

from stubpy._constants import ENUM_BASE_NAMES
from stubpy.analysis.harvest.models import ClassInfo, VariableInfo
from stubpy.resolve.static import literal_default
from stubpy.state.context import StubContext

from ._names import bare_final_default
from .annotations.defaults import ELLIPSIS, render_default
from .annotations.style import style_text
from .decorators import decorator_base_name

_FIELD_DEFAULT_BASES: frozenset[str] = frozenset({"NamedTuple"})


def _base_names(ci: ClassInfo) -> set[str]:
    return {b.split("[")[0].rpartition(".")[2] for b in ci.bases}


def _enum_member_line(attr: VariableInfo, members: dict[str, str], indent: str) -> str:
    """Return ``NAME = literal``, ``ALIAS = NAME`` or ``NAME = ...``; *members* maps rendered values to first names.

    A member repeating an earlier literal value is an alias, as at runtime.
    """
    value = attr.value_repr or ""
    if value in members.values():
        return f"{indent}{attr.name} = {value}"
    rendered = render_default(literal_default(value)) if value else ELLIPSIS
    if rendered != ELLIPSIS and rendered in members:
        return f"{indent}{attr.name} = {members[rendered]}"
    members.setdefault(rendered if rendered != ELLIPSIS else f"<{attr.name}>", attr.name)
    return f"{indent}{attr.name} = {rendered}"


def attribute_lines(ci: ClassInfo, ctx: StubContext, indent: str) -> list[str]:
    """Return the class-body attribute lines: enum members, annotated fields, typed literals."""
    bases = _base_names(ci)
    is_enum = bool(bases & ENUM_BASE_NAMES)
    keeps_defaults = bool(bases & _FIELD_DEFAULT_BASES) or any(
        decorator_base_name(d) == "dataclass" for d in ci.decorators
    )
    lines: list[str] = []
    members: dict[str, str] = {}
    for attr in ci.attributes:
        name = attr.name
        if name == "__hash__" and attr.value_repr == "None":
            lines.append(f"{indent}__hash__: ClassVar[None]  # type: ignore[assignment]")
            continue
        if name.startswith("__") or (is_enum and name.startswith("_") and name.endswith("_")):
            continue
        if name.startswith("_") and not ctx.config.include_private and not is_enum:
            continue
        if is_enum and attr.annotation_str is None:
            lines.append(_enum_member_line(attr, members, indent))
        elif attr.annotation_str is not None:
            text = style_text(attr.annotation_str, ctx)
            default = " = ..." if keeps_defaults and attr.value_repr is not None else bare_final_default(text, attr.value_repr)
            lines.append(f"{indent}{name}: {text}{default}")
        elif attr.inferred_type_str and attr.inferred_type_str != "None":
            lines.append(f"{indent}{name}: {attr.inferred_type_str}")
    return lines
