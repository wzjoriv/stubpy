"""
Module-level function stubs.
"""
from __future__ import annotations

import copy
import inspect

from stubpy.analysis.docstrings import parse_docstring_types
from stubpy.analysis.harvest.models import FunctionInfo
from stubpy.analysis.hints import returns_hint, signature_hint
from stubpy.analysis.symbols.models import FunctionSymbol
from stubpy.emit._constants import ASYNC_ITERATOR_RETURN, FUNCTION_SOURCE_DECORATORS
from stubpy.resolve import (
    ParamWithHints,
    get_hints_for_method,
    resolve_function_params,
    signature_of,
    unwrap_callable,
)
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Stage

from ._ast_params import build_ast_only_params
from ._branch_overloads import branch_overloads
from ._def_layout import format_def, hinted_def
from ._inferred import inferred_return_text, with_callee_types
from ._overload_forward import forwarded_python_overloads
from ._reads import with_reads
from ._static import refine_live, static_params
from ._variadic_notes import forwarding_callees, note_compiled_overloads, warn_dynamic_kwargs
from .annotations import format_param
from .annotations.params import is_plain_annotation, raw_key
from .annotations.source import hint_text
from .annotations.style import style_text
from .decorators import decorator_base_name, stub_decorators
from .docstrings import docstring_block, make_docstring_body
from .methods import function_ast_infos
from .signature import generic_name, infer_default_type, render_params, structural_return, with_separators


def _live_params(sym: FunctionSymbol, ctx: StubContext) -> list[ParamWithHints]:
    """Return the live function's params, resolving variadics unless the config disables it."""
    live_fn = sym.live_func
    if getattr(ctx.config, "resolve_kwargs", True) and getattr(ctx.config, "resolve_args", True):
        params = resolve_function_params(
            live_fn,
            sym.ast_info,
            ctx.module_namespace,
            ast_info_by_name=function_ast_infos(ctx),
        )
        return refine_live(params, sym.ast_info, ctx)
    sig = signature_of(live_fn)
    own_params = list(sig.parameters.values()) if sig is not None else []
    own_hints = get_hints_for_method(live_fn)
    return [(p, own_hints) for p in own_params]


def _inferred_param_types(sym: FunctionSymbol, ctx: StubContext) -> dict[str, str]:
    """Collect param types from the docstring and from literal defaults (AST-only or ``--infer-types``)."""
    infer = getattr(ctx.config, "infer_types", False)
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
                    Stage.EMIT,
                    sym.name,
                    f"Docstring type inference: {len(types)} param type(s)"
                    + (f", return={ds_ret}" if ds_ret else ""),
                )
    if sym.ast_info is not None and (live_fn is None or infer):
        for pname, ptype in getattr(sym.ast_info, "raw_arg_inferred_types", {}).items():
            if pname not in types:
                types[pname] = ptype
    return types


def _docstring_return(live_fn: object) -> str:
    """Return the docstring's return type when it is a plain annotation, else ``""``."""
    doc = getattr(live_fn, "__doc__", None)
    returns = parse_docstring_types(doc).returns if isinstance(doc, str) else None
    return returns if returns and is_plain_annotation(returns) else ""


def _with_info(sym: FunctionSymbol, info: FunctionInfo) -> FunctionSymbol:
    """A copy of *sym* carrying *info*."""
    out = copy.copy(sym)
    out.ast_info = info
    return out


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

    See Also
    --------
    generate_method_stub : The equivalent for class members.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> info = ast_harvest("def greet(name: str) -> str: ...").functions[0]
    >>> generate_function_stub(FunctionSymbol("greet", 1, ast_info=info), StubContext())
    'def greet(name: str) -> str: ...'
    """
    live_fn = sym.live_func
    is_async = sym.is_async
    is_agen = sym.ast_info is not None and sym.ast_info.is_async_generator
    if live_fn is not None:
        candidates = (live_fn, unwrap_callable(live_fn))
        is_agen = is_agen or any(inspect.isasyncgenfunction(f) for f in candidates)
        is_async = (is_async or any(inspect.iscoroutinefunction(f) for f in candidates)) and not is_agen
    keyword = "async def" if is_async else "def"
    decorators = [
        f"@{d}" for d in stub_decorators(sym.ast_info.decorators if sym.ast_info is not None else [])
        if decorator_base_name(d) in FUNCTION_SOURCE_DECORATORS
    ]

    body = "..."
    if getattr(ctx.config, "include_docstrings", False) and live_fn is not None:
        body = make_docstring_body(unwrap_callable(live_fn), "    ")
    elif getattr(ctx.config, "include_docstrings", False) and sym.ast_info is not None:
        body = docstring_block(sym.ast_info.docstring, "    ")

    sig_text = signature_hint(live_fn, sym.ast_info)
    hinted = hinted_def("", keyword, sym.name, sig_text, ctx, body) if sig_text else None
    if hinted is not None:
        return "\n".join(decorators + hinted)
    py_overloads = forwarded_python_overloads(sym.ast_info, ctx, keyword=keyword)
    if py_overloads is not None:
        return "\n".join(decorators + py_overloads)
    branched = branch_overloads(sym.ast_info, ctx, lambda info: generate_function_stub(
        _with_info(sym, info), ctx).split("\n"))
    if branched is not None:
        return "\n".join(branched)

    raw_anns: dict[str, str] = sym.ast_info.raw_arg_annotations if sym.ast_info is not None else {}

    if live_fn is not None:
        ret_str = hint_text(live_fn, "return", ctx)
        params_with_hints = _live_params(sym, ctx)
    else:
        ret_str = ""
        resolved = static_params(sym.ast_info, ctx) if sym.ast_info is not None else None
        params_with_hints = resolved if resolved is not None else build_ast_only_params(sym.ast_info)

    if not ret_str and sym.ast_info and sym.ast_info.raw_return_annotation:
        ret_str = style_text(sym.ast_info.raw_return_annotation, ctx)
    ret_str = returns_hint(live_fn, sym.ast_info) or ret_str or structural_return(sym.ast_info) or (
        ASYNC_ITERATOR_RETURN if is_agen else inferred_return_text(sym.ast_info, ctx)
    )
    if not ret_str and getattr(ctx.config, "infer_types", False):
        ret_str = _docstring_return(live_fn)

    params_with_hints = with_reads(params_with_hints, sym.ast_info)
    warn_dynamic_kwargs(sym.name, params_with_hints, sym.ast_info, ctx)
    note_compiled_overloads(sym.name, params_with_hints, forwarding_callees(sym.ast_info, ctx.module_namespace), ctx)
    params_with_hints = with_separators(params_with_hints)
    types = with_callee_types(params_with_hints, live_fn, sym.ast_info, _inferred_param_types(sym, ctx))

    param_strs = render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx,
        raw_ann_override=raw_anns.get(raw_key(p)),
        docstring_type=types.get(p.name) if types else None,
        inferred_type=infer_default_type(p, types),
    ))
    ret_part = f" -> {ret_str}" if ret_str else ""
    return "\n".join(decorators + format_def("", keyword, generic_name(sym.name, sym.ast_info), param_strs, ret_part, len(param_strs), body))
