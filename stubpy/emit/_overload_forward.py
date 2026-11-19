"""A function that only forwards ``*args`` (and ``**kwargs``) to an ``@overload``-ed Python callee gets its variants."""
from __future__ import annotations

from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Stage
from stubpy.resolve.static import ClassRef, FuncRef, SourceHints, own_params, static_mro

from ._static import bind_foreign, bind_names, names_in, resolver_of
from .annotations import format_param
from .annotations.style import style_text
from .signature import format_def, receiver_text, render_params, with_separators


def _only_forwards(info: FunctionInfo, method: bool) -> tuple[str, bool] | None:
    """Return ``(callee, args_only)`` when *info* passes ``*args`` (and ``**kwargs``) unchanged to one callee."""
    params = info.raw_params[1:] if method else info.raw_params
    kinds = [p.kind for p in params]
    if kinds not in (["VAR_POSITIONAL", "VAR_KEYWORD"], ["VAR_POSITIONAL"]) or info.hint_signature:
        return None
    kw = info.kwargs_forwarded_to + info.kwargs_method_targets
    pos = info.args_forwarded_to + info.args_method_targets
    args_only = kinds == ["VAR_POSITIONAL"]
    if len(pos) != 1 or (kw != pos and not args_only) or (args_only and kw):
        return None
    target = pos[0]
    if (info.kwargs_positional_skips.get(target) or info.kwargs_explicit_names.get(target) or info.kwargs_consumed
            or info.kwargs_injected or info.kwargs_dynamic or info.kwargs_unknown_starred):
        return None
    return target, args_only


def _callee(info: FunctionInfo, target: str, owner: ClassInfo | None, ctx: StubContext) -> FuncRef | None:
    """Resolve the forwarding target of *info* to a function or method in the source index."""
    resolver = resolver_of(ctx.source_index)
    module = ctx.source_module
    if owner is None:
        ref = resolver.names.dotted(module, target, info)
        return ref if isinstance(ref, FuncRef) else None
    cref = ClassRef(module, owner)
    if target in info.kwargs_method_targets:
        return resolver.names.inherited_method(cref, target)
    if target == info.name:
        for parent in static_mro(resolver.names, cref)[1:]:
            if not isinstance(parent, ClassRef):
                return None
            found = resolver.names.attribute(parent, target)
            if found is not None:
                return found if isinstance(found, FuncRef) else None
        return None
    ref = resolver.names.dotted(module, target, info)
    return ref if isinstance(ref, FuncRef) else None


def forwarded_python_overloads(info: FunctionInfo | None, ctx: StubContext, indent: str = "",
                               owner: ClassInfo | None = None, receiver: str = "self",
                               keyword: str = "def") -> list[str] | None:
    """The ``@overload`` variants of the overloaded callee that *info* forwards ``*args, **kwargs`` to unchanged.

    ``None`` when *info* does anything else, or the callee is not an
    ``@overload``-ed function or method found in the source index.
    """
    if info is None or ctx.source_module is None or ctx.source_index is None:
        return None
    found = _only_forwards(info, owner is not None)
    target, args_only = found if found is not None else (None, False)
    callee = _callee(info, target, owner, ctx) if target is not None else None
    if callee is None or len(callee.overloads) < 2:
        return None
    lines: list[str] = []
    for variant in callee.overloads:
        hints = SourceHints(callee.module)
        params = [bind_foreign(p, hints, ctx) for p in own_params(variant, method=callee.owner is not None)]
        if args_only:
            params = _positional(params)
            if params is None:
                continue
        strs = render_params(with_separators(params), lambda p, h: format_param(p, h, ctx))
        ret = info.raw_return_annotation or variant.raw_return_annotation or ""
        if ret and ret is variant.raw_return_annotation and callee.module is not ctx.source_module:
            names = names_in(ret)
            ret = ret if names is not None and bind_names(names, callee.module, ctx) else ""
        prefix = [receiver_text(receiver, "")] if owner is not None else []
        ret_part = f" -> {style_text(ret, ctx)}" if ret else ""
        lines.append(f"{indent}@overload")
        lines += format_def(indent, keyword, info.name, prefix + strs, ret_part, len(strs))
    ctx.extra_imports.setdefault("overload", "from typing import overload")
    ctx.diagnostics.info(Stage.RESOLVE, info.name, f"forwards to {target} with {len(callee.overloads)} overloads; "
                         "copied as @overload variants")
    return lines


def _positional(params: list) -> list | None:
    """The variant as ``*args`` alone can call it: positional-only, keywords dropped; ``None`` if one is required."""
    out = []
    for p, h in params:
        if p.kind in (p.KEYWORD_ONLY, p.VAR_KEYWORD):
            if p.kind == p.KEYWORD_ONLY and p.default is p.empty:
                return None
            continue
        out.append((p.replace(kind=p.POSITIONAL_ONLY) if p.kind == p.POSITIONAL_OR_KEYWORD else p, h))
    return out
