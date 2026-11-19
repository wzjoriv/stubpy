"""AST-only emission: signatures and class stubs synthesised without a live module."""
from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap
from typing import Any

from stubpy._constants import ASYNC_ITERATOR_RETURN, IMPLICIT_CLASSMETHODS, PUBLIC_DUNDERS
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo, RawParam
from stubpy.core.context import StubContext
from stubpy.resolve import ParamWithHints

from ._ast_attributes import attribute_lines
from ._inherited_property import inherited_accessor
from ._instance_attrs import declared_names, source_attribute_lines
from ._overload_forward import forwarded_python_overloads
from ._static import static_params
from .annotations import format_param
from .annotations.defaults import NonLiteralDefault
from .annotations.params import raw_key
from .annotations.style import style_text
from .branches import Unit, join_sections, weave
from .decorators import decorator_base_name, stub_decorators
from .docstrings import docstring_block
from .signature import (
    format_def,
    generic_name,
    hinted_def,
    receiver_text,
    render_params,
    structural_return,
    warn_dynamic_kwargs,
    with_separators,
)

_KINDS = {
    "POSITIONAL_ONLY": inspect.Parameter.POSITIONAL_ONLY,
    "POSITIONAL_OR_KEYWORD": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "VAR_POSITIONAL": inspect.Parameter.VAR_POSITIONAL,
    "KEYWORD_ONLY": inspect.Parameter.KEYWORD_ONLY,
    "VAR_KEYWORD": inspect.Parameter.VAR_KEYWORD,
}


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


def emit_method_from_ast(minfo: FunctionInfo, ctx: StubContext, indent: str = "    ",
                         owner: ClassInfo | None = None) -> list[str]:
    """Return the stub lines of a method from its :class:`FunctionInfo`; only stub-relevant decorators are kept.

    With its *owner* class, variadics are resolved from source when the module was not imported.
    """
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
    if owner is not None and not is_sta:
        py_overloads = forwarded_python_overloads(minfo, ctx, indent, owner, "cls" if is_cls else "self", keyword)
        if py_overloads is not None:
            return lines + py_overloads

    raw_anns = minfo.raw_arg_annotations or {}
    inferred = getattr(minfo, "raw_arg_inferred_types", {}) or {}
    ret_str = minfo.hint_returns or style_text(minfo.raw_return_annotation, ctx) or (
        structural_return(minfo) or (ASYNC_ITERATOR_RETURN if minfo.is_async_generator else "")
    ) or ("None" if minfo.name == "__init__" and owner is not None else "")

    raw_params = list(minfo.raw_params)
    receiver = ""
    if not is_sta and raw_params and raw_params[0].kind in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"):
        receiver = raw_anns.get(raw_params[0].name) or ""
        raw_params = raw_params[1:]
    resolved = static_params(minfo, ctx, owner) if owner is not None else None
    if resolved is not None:
        warn_dynamic_kwargs(f"{owner.name}.{minfo.name}", resolved, minfo, ctx)
    params_with_hints = with_separators(
        resolved if resolved is not None else params_from_raw(raw_params, skip_receiver_names=False)
    )
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


def keeps_method(name: str, ctx: StubContext) -> bool:
    """True when a method named *name* belongs in a stub: public dunders, and private names only on request."""
    if name.startswith("__") and name.endswith("__"):
        return name in PUBLIC_DUNDERS
    return not name.startswith("_") or ctx.config.include_private


def method_lines(ci: ClassInfo, ctx: StubContext, indent: str, owner: ClassInfo | None = None) -> list[str]:
    """Return method stub lines, dropping an implementation that has ``@overload`` variants; *owner* defaults to *ci*."""
    owner = owner if owner is not None else ci
    overloaded = {m.name for m in ci.methods if m.is_overload}
    lines: list[str] = []
    variants: set[tuple[str, ...]] = set()
    for minfo in ci.methods:
        if (minfo.name in overloaded and not minfo.is_overload) or minfo.hint_ignore:
            continue
        if minfo.is_overload:
            key = tuple(emit_method_from_ast(minfo, ctx, indent))
            if key in variants:
                continue
            variants.add(key)
        if keeps_method(minfo.name, ctx):
            accessor = inherited_accessor(minfo, ci, ctx, indent)
            if accessor is not None:
                lines.extend(accessor[0])
                minfo = accessor[1]
            lines.extend(emit_method_from_ast(minfo, ctx, indent, owner))
    return lines


def branch_groups(ci: ClassInfo) -> list[tuple[tuple, ClassInfo]]:
    """Return ``(branch, members)`` per version branch of the class body, in source order."""
    groups: dict[tuple, ClassInfo] = {}
    for kind in ("attributes", "methods", "classes"):
        for item in getattr(ci, kind):
            if item.branch:
                group = groups.setdefault(item.branch, dataclasses.replace(ci, attributes=[], methods=[], classes=[]))
                getattr(group, kind).append(item)
    first = {path: min(i.lineno for k in ("attributes", "methods", "classes") for i in getattr(g, k))
             for path, g in groups.items()}
    return sorted(groups.items(), key=lambda item: first[item[0]])


def unbranched(ci: ClassInfo) -> ClassInfo:
    """Return *ci* without the members that sit in version branches."""
    return dataclasses.replace(
        ci, attributes=[a for a in ci.attributes if not a.branch], methods=[m for m in ci.methods if not m.branch],
        classes=[c for c in ci.classes if not c.branch],
    )


def _nested_lines(ci: ClassInfo, ctx: StubContext, indent: str) -> list[str]:
    return [
        emit_class_from_ast(nested, ctx, indent) for nested in ci.classes
        if not nested.hint_ignore and (ctx.config.include_private or not nested.name.startswith("_"))
    ]


def member_text(group: ClassInfo, ctx: StubContext) -> str:
    """Return the unindented stubs of one branch's members: attributes, nested classes, then methods."""
    lines = attribute_lines(group, ctx, "") + _nested_lines(group, ctx, "")
    methods = method_lines(group, ctx, "")
    return "\n".join(lines + ([""] if lines and methods else []) + methods)


def branch_lines(units: list[Unit], indent: str) -> list[str]:
    """Return the version blocks of *units*, indented by *indent*."""
    text = join_sections(weave(units))
    return textwrap.indent(text, indent).split("\n") if text else []


def emit_class_from_ast(ci: ClassInfo, ctx: StubContext, indent: str = "") -> str:
    """Return a class stub built from :class:`ClassInfo`: decorators, bases, attributes, nested classes and methods.

    Members inside version branches follow, wrapped in their ``if`` blocks.
    """
    groups = branch_groups(ci)
    ci = unbranched(ci) if groups else ci
    base_str = f"({', '.join(ci.bases)})" if ci.bases else ""
    lines: list[str] = [f"{indent}@{d}" for d in stub_decorators(ci.decorators)]
    lines.append(f"{indent}class {generic_name(ci.name, ci)}{base_str}:")
    inner = indent + "    "

    body = attribute_lines(ci, ctx, inner)
    body += source_attribute_lines(ci, declared_names(body, ci), ctx, inner)
    if ctx.config.include_docstrings and ci.docstring and ci.docstring.strip():
        doc = docstring_block(ci.docstring, inner)
        body.insert(0, f"{inner}{doc}")
        if len(body) > 1:
            body.insert(1, "")
    body.extend(_nested_lines(ci, ctx, inner))
    methods = method_lines(ci, ctx, inner)
    if body and methods:
        body.append("")
    body.extend(methods)
    blocks = branch_lines([Unit(member_text(g, ctx), False, path) for path, g in groups], inner)
    if body and blocks:
        body.append("")
    body.extend(blocks)
    lines.extend(body or [f"{inner}..."])
    return "\n".join(lines)
