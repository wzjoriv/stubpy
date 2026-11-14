"""Module-level function stubs."""
from __future__ import annotations

import inspect

from stubpy.analysis.docstrings import parse_docstring_types
from stubpy.analysis.symbols.models import FunctionSymbol
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import DiagnosticStage
from stubpy.resolve import (
    ParamWithHints,
    get_hints_for_method,
    resolve_function_params,
    signature_of,
    unwrap_callable,
)

from .annotations import annotation_to_str, format_param
from .ast_only import build_ast_only_params
from .decorators import decorator_base_name, stub_decorators
from .docstrings import make_docstring_body
from .methods import function_ast_infos
from .signature import (
    format_def,
    infer_default_type,
    raw_key,
    render_params,
    warn_dynamic_kwargs,
    with_separators,
)


def _live_params(sym: FunctionSymbol, ctx: StubContext) -> list[ParamWithHints]:
    """Return the live function's params, resolving variadics unless the config disables it."""
    live_fn = sym.live_func
    if getattr(ctx.config, "resolve_kwargs", True) and getattr(ctx.config, "resolve_args", True):
        return resolve_function_params(
            live_fn,
            sym.ast_info,
            ctx.module_namespace,
            ast_info_by_name=function_ast_infos(ctx),
        )
    sig = signature_of(live_fn)
    own_params = list(sig.parameters.values()) if sig is not None else []
    own_hints = get_hints_for_method(live_fn)
    return [(p, own_hints) for p in own_params]


def _inferred_param_types(sym: FunctionSymbol, ctx: StubContext) -> dict[str, str]:
    """Collect param types from the docstring and from literal defaults (AST-only or ``--infer-types``)."""
    infer = getattr(ctx.config, "infer_types_from_docstrings", False)
    live_fn = sym.live_func
    types: dict[str, str] = {}
    ds_ret: str | None = None
    if infer and live_fn is not None:
        doc = getattr(live_fn, "__doc__", None)
        if doc:
            parsed = parse_docstring_types(doc)
            types = parsed.params
            ds_ret = parsed.returns
            if types or ds_ret:
                ctx.diagnostics.info(
                    DiagnosticStage.EMIT,
                    sym.name,
                    f"Docstring type inference: {len(types)} param type(s)"
                    + (f", return={ds_ret}" if ds_ret else ""),
                )
    if sym.ast_info is not None and (live_fn is None or infer):
        for pname, ptype in getattr(sym.ast_info, "raw_arg_inferred_types", {}).items():
            if pname not in types:
                types[pname] = ptype
    return types


def generate_function_stub(sym: FunctionSymbol, ctx: StubContext) -> str:
    """Generate the stub for a module-level function.

    Emits ``async def`` when needed, expands forwarded ``**kwargs`` /
    ``*args``, and prefers raw source annotations where they keep alias names
    that runtime evaluation would lose.

    Parameters
    ----------
    sym : FunctionSymbol
        The function symbol.
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        One or more stub lines.
    """
    live_fn = sym.live_func
    is_async = sym.is_async
    if not is_async and live_fn is not None:
        is_async = any(
            inspect.iscoroutinefunction(f) or inspect.isasyncgenfunction(f)
            for f in (live_fn, unwrap_callable(live_fn))
        )
    keyword = "async def" if is_async else "def"
    decorators = [
        f"@{d}" for d in stub_decorators(sym.ast_info.decorators if sym.ast_info is not None else [])
        if decorator_base_name(d) == "deprecated"
    ]

    raw_anns: dict[str, str] = sym.ast_info.raw_arg_annotations if sym.ast_info is not None else {}

    if live_fn is not None:
        hints = get_hints_for_method(live_fn)
        ret_str = annotation_to_str(hints.get("return", inspect.Parameter.empty), ctx)
        params_with_hints = _live_params(sym, ctx)
    else:
        ret_str = ""
        params_with_hints = build_ast_only_params(sym.ast_info)

    if not ret_str and sym.ast_info and sym.ast_info.raw_return_annotation:
        ret_str = sym.ast_info.raw_return_annotation

    warn_dynamic_kwargs(sym.name, params_with_hints, sym.ast_info, ctx)
    params_with_hints = with_separators(params_with_hints)
    types = _inferred_param_types(sym, ctx)

    param_strs = render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx,
        raw_ann_override=raw_anns.get(raw_key(p)),
        docstring_type=types.get(p.name) if types else None,
        inferred_type=infer_default_type(p, types),
    ))
    ret_part = f" -> {ret_str}" if ret_str else ""

    body = "..."
    if getattr(ctx.config, "include_docstrings", False) and live_fn is not None:
        body = make_docstring_body(unwrap_callable(live_fn), "    ")

    return "\n".join(decorators + format_def("", keyword, sym.name, param_strs, ret_part, len(param_strs), body))
