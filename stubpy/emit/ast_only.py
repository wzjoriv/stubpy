"""AST-only emission: signatures and class stubs synthesised without a live module."""
from __future__ import annotations

import ast
import inspect
from typing import Any

from stubpy._constants import ASYNC_ITERATOR_RETURN, ENUM_BASE_NAMES, IMPLICIT_CLASSMETHODS, PUBLIC_DUNDERS
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo, RawParam, VariableInfo
from stubpy.core.context import StubContext
from stubpy.resolve import ParamWithHints

from .annotations import format_param
from .annotations.defaults import ELLIPSIS, NonLiteralDefault, render_default
from .annotations.params import raw_key
from .annotations.style import style_text
from .decorators import decorator_base_name, stub_decorators
from .docstrings import docstring_block
from .signature import format_def, generic_name, hinted_def, receiver_text, render_params, with_separators

_KINDS = {
    "POSITIONAL_ONLY": inspect.Parameter.POSITIONAL_ONLY,
    "POSITIONAL_OR_KEYWORD": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "VAR_POSITIONAL": inspect.Parameter.VAR_POSITIONAL,
    "KEYWORD_ONLY": inspect.Parameter.KEYWORD_ONLY,
    "VAR_KEYWORD": inspect.Parameter.VAR_KEYWORD,
}
_FIELD_DEFAULT_BASES: frozenset[str] = frozenset({"NamedTuple"})


def _literal_default(text: str) -> Any:
    """Evaluate a literal default, or wrap a non-literal one in :class:`NonLiteralDefault`."""
    try:
        return ast.literal_eval(text)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return NonLiteralDefault(text)


def params_from_raw(raw_params: list[RawParam], skip_receiver_names: bool = True) -> list[ParamWithHints]:
    """Build ``inspect.Parameter`` objects from harvested :class:`RawParam` entries.

    ``self`` / ``cls`` are skipped unless *skip_receiver_names* is false.
    Literal defaults are evaluated; other defaults become
    :class:`NonLiteralDefault`.  An explicit annotation wins over one
    inferred from the default.
    """
    result: list[ParamWithHints] = []
    for rp in raw_params:
        if skip_receiver_names and rp.name in ("self", "cls"):
            continue
        kind = _KINDS.get(rp.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        default: Any = inspect.Parameter.empty
        if rp.default_repr is not None:
            default = _literal_default(rp.default_repr)
        annotation: Any = inspect.Parameter.empty
        if rp.annotation_str:
            annotation = rp.annotation_str
        elif rp.inferred_type_str:
            annotation = rp.inferred_type_str
        result.append((inspect.Parameter(rp.name, kind, default=default, annotation=annotation), {}))
    return result


def build_ast_only_params(ast_info: Any | None) -> list[ParamWithHints]:
    """Reconstruct a function's parameters from AST data alone.

    Uses ``raw_params`` when present, otherwise falls back to the
    unordered ``raw_arg_annotations`` mapping.
    """
    if ast_info is None:
        return []

    raw_params = getattr(ast_info, "raw_params", None)
    if raw_params:
        return params_from_raw(raw_params)

    raw_anns: dict[str, str] = getattr(ast_info, "raw_arg_annotations", {})
    params: list[ParamWithHints] = []
    seen: set[str] = set()
    for raw_name, ann_str in raw_anns.items():
        if raw_name.startswith("**"):
            kind = inspect.Parameter.VAR_KEYWORD
            name = raw_name[2:]
        elif raw_name.startswith("*"):
            kind = inspect.Parameter.VAR_POSITIONAL
            name = raw_name[1:]
        else:
            kind = inspect.Parameter.POSITIONAL_OR_KEYWORD
            name = raw_name
        if name in ("self", "cls") or name in seen:
            continue
        seen.add(name)
        params.append((inspect.Parameter(name, kind, annotation=ann_str), {}))
    return params


def emit_method_from_ast(minfo: FunctionInfo, ctx: StubContext, indent: str = "    ") -> list[str]:
    """Return the stub lines of a method from its :class:`FunctionInfo`; only stub-relevant decorators are kept."""
    decorators = stub_decorators(minfo.decorators)
    bases = {decorator_base_name(d) for d in decorators}
    implicit = minfo.name in IMPLICIT_CLASSMETHODS
    is_cls = "classmethod" in bases or implicit
    is_sta = "staticmethod" in bases and not implicit
    keyword = "async def" if minfo.is_async else "def"
    body = docstring_block(minfo.docstring, indent + "    ") if ctx.config.include_docstrings else "..."

    lines = [f"{indent}@{dec}" for dec in decorators]
    hinted = hinted_def(indent, keyword, minfo.name, minfo.hint_signature, ctx, body) if minfo.hint_signature else None
    if hinted is not None:
        return lines + hinted

    raw_anns = minfo.raw_arg_annotations or {}
    inferred = getattr(minfo, "raw_arg_inferred_types", {}) or {}
    ret_str = minfo.hint_returns or style_text(minfo.raw_return_annotation, ctx) or (
        ASYNC_ITERATOR_RETURN if minfo.is_async_generator else ""
    )

    raw_params = list(minfo.raw_params)
    receiver = ""
    if not is_sta and raw_params and raw_params[0].kind in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"):
        receiver = raw_anns.get(raw_params[0].name) or ""
        raw_params = raw_params[1:]
    params_with_hints = with_separators(params_from_raw(raw_params, skip_receiver_names=False))
    self_prefix = [] if is_sta else [receiver_text("cls" if is_cls else "self", receiver)]
    param_strs = self_prefix + render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx,
        raw_ann_override=raw_anns.get(raw_key(p)),
        inferred_type=inferred.get(p.name),
    ))
    ret_part = f" -> {ret_str}" if ret_str else ""

    n_params = len(param_strs) - len(self_prefix)
    lines.extend(format_def(indent, keyword, generic_name(minfo.name, minfo), param_strs, ret_part, n_params, body))
    return lines


def _base_names(ci: ClassInfo) -> set[str]:
    return {b.split("[")[0].rpartition(".")[2] for b in ci.bases}


def _enum_member_line(attr: VariableInfo, members: dict[str, str], indent: str) -> str:
    """Return ``NAME = literal``, ``ALIAS = NAME`` or ``NAME = ...``; *members* maps rendered values to first names.

    A member repeating an earlier literal value is an alias, as at runtime.
    """
    value = attr.value_repr or ""
    if value in members.values():
        return f"{indent}{attr.name} = {value}"
    rendered = render_default(_literal_default(value)) if value else ELLIPSIS
    if rendered != ELLIPSIS and rendered in members:
        return f"{indent}{attr.name} = {members[rendered]}"
    members.setdefault(rendered if rendered != ELLIPSIS else f"<{attr.name}>", attr.name)
    return f"{indent}{attr.name} = {rendered}"


def _attribute_lines(ci: ClassInfo, ctx: StubContext, indent: str) -> list[str]:
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
            lines.append(f"{indent}__hash__: ClassVar[None]")
            continue
        if name.startswith("__") or (is_enum and name.startswith("_") and name.endswith("_")):
            continue
        if name.startswith("_") and not ctx.config.include_private and not is_enum:
            continue
        if is_enum and attr.annotation_str is None:
            lines.append(_enum_member_line(attr, members, indent))
        elif attr.annotation_str is not None:
            default = " = ..." if keeps_defaults and attr.value_repr is not None else ""
            lines.append(f"{indent}{name}: {style_text(attr.annotation_str, ctx)}{default}")
        elif attr.inferred_type_str and attr.inferred_type_str != "None":
            lines.append(f"{indent}{name}: {attr.inferred_type_str}")
    return lines


def _method_lines(ci: ClassInfo, ctx: StubContext, indent: str) -> list[str]:
    """Return method stub lines, dropping an implementation that has ``@overload`` variants."""
    overloaded = {m.name for m in ci.methods if m.is_overload}
    lines: list[str] = []
    for minfo in ci.methods:
        if (minfo.name in overloaded and not minfo.is_overload) or minfo.hint_ignore:
            continue
        name = minfo.name
        if name.startswith("__") and name.endswith("__"):
            if name not in PUBLIC_DUNDERS:
                continue
        elif name.startswith("_") and not ctx.config.include_private:
            continue
        lines.extend(emit_method_from_ast(minfo, ctx, indent))
    return lines


def emit_class_from_ast(ci: ClassInfo, ctx: StubContext, indent: str = "") -> str:
    """Return a class stub built from :class:`ClassInfo`: decorators, bases, attributes, nested classes and methods."""
    base_str = f"({', '.join(ci.bases)})" if ci.bases else ""
    lines: list[str] = [f"{indent}@{d}" for d in stub_decorators(ci.decorators)]
    lines.append(f"{indent}class {generic_name(ci.name, ci)}{base_str}:")
    inner = indent + "    "

    body = _attribute_lines(ci, ctx, inner)
    if ctx.config.include_docstrings and ci.docstring and ci.docstring.strip():
        doc = docstring_block(ci.docstring, inner)
        body.insert(0, f"{inner}{doc}")
        if len(body) > 1:
            body.insert(1, "")
    for nested in ci.classes:
        if not nested.hint_ignore and (ctx.config.include_private or not nested.name.startswith("_")):
            body.append(emit_class_from_ast(nested, ctx, inner))
    methods = _method_lines(ci, ctx, inner)
    if body and methods:
        body.append("")
    body.extend(methods)
    lines.extend(body or [f"{inner}..."])
    return "\n".join(lines)
