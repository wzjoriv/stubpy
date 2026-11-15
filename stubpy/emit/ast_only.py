"""AST-only emission: signatures and class stubs synthesised without a live module."""
from __future__ import annotations

import ast
import inspect
from typing import Any

from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo, RawParam
from stubpy.core.context import StubContext
from stubpy.resolve import ParamWithHints

from .annotations import format_param
from .annotations.defaults import NonLiteralDefault
from .signature import format_def, raw_key, render_params, with_separators

_KINDS = {
    "POSITIONAL_ONLY": inspect.Parameter.POSITIONAL_ONLY,
    "POSITIONAL_OR_KEYWORD": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "VAR_POSITIONAL": inspect.Parameter.VAR_POSITIONAL,
    "KEYWORD_ONLY": inspect.Parameter.KEYWORD_ONLY,
    "VAR_KEYWORD": inspect.Parameter.VAR_KEYWORD,
}


def params_from_raw(raw_params: list[RawParam]) -> list[ParamWithHints]:
    """Build ``inspect.Parameter`` objects from harvested :class:`RawParam` entries.

    ``self`` / ``cls`` are skipped.  Literal defaults are evaluated; other
    defaults become :class:`NonLiteralDefault`.  An explicit annotation wins
    over one inferred from the default.
    """
    result: list[ParamWithHints] = []
    for rp in raw_params:
        if rp.name in ("self", "cls"):
            continue
        kind = _KINDS.get(rp.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        default: Any = inspect.Parameter.empty
        if rp.default_repr is not None:
            try:
                default = ast.literal_eval(rp.default_repr)
            except (ValueError, TypeError):
                default = NonLiteralDefault(rp.default_repr)
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
    """Return the stub lines of a method from its :class:`FunctionInfo`."""
    is_cls = "classmethod" in minfo.decorators
    is_sta = "staticmethod" in minfo.decorators
    keyword = "async def" if minfo.is_async else "def"

    lines = [f"{indent}@{dec}" for dec in minfo.decorators]

    raw_anns = minfo.raw_arg_annotations or {}
    inferred = getattr(minfo, "raw_arg_inferred_types", {}) or {}
    ret_str = minfo.raw_return_annotation or ""

    params_with_hints = with_separators(build_ast_only_params(minfo))
    self_prefix = [] if is_sta else (["cls"] if is_cls else ["self"])
    param_strs = self_prefix + render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx,
        raw_ann_override=raw_anns.get(raw_key(p)),
        inferred_type=inferred.get(p.name),
    ))
    ret_part = f" -> {ret_str}" if ret_str else ""

    n_params = len([s for s in param_strs if s not in ("self", "cls")])
    lines.extend(format_def(indent, keyword, minfo.name, param_strs, ret_part, n_params))
    return lines


def emit_class_from_ast(ci: ClassInfo, ctx: StubContext) -> str:
    """Return a class stub built from :class:`ClassInfo`: decorators, bases and method signatures."""
    base_str = f"({', '.join(ci.bases)})" if ci.bases else ""
    lines: list[str] = [f"@{d}" for d in ci.decorators if d] + [f"class {ci.name}{base_str}:"]

    if not ci.methods:
        lines.append("    ...")
        return "\n".join(lines)

    for minfo in ci.methods:
        lines.extend(emit_method_from_ast(minfo, ctx))
    return "\n".join(lines)
