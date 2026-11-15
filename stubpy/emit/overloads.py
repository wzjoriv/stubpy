"""``@overload`` group stubs."""
from __future__ import annotations

import inspect

from stubpy.analysis.symbols.models import FunctionSymbol, OverloadGroup
from stubpy.core.context import StubContext
from stubpy.resolve import get_hints_for_method

from .annotations import annotation_to_str, format_param
from .ast_only import build_ast_only_params
from .signature import format_def, raw_key, render_params, with_separators


def generate_overload_group_stub(group: OverloadGroup, ctx: StubContext) -> str:
    """Emit one ``@overload`` stub per variant in *group*.

    The implementation itself is left out, per PEP 484; the pipeline
    suppresses its plain function stub.

    Parameters
    ----------
    group : OverloadGroup
        The overload group.
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        The variant stubs separated by blank lines, or ``""`` without variants.
    """
    if not group.variants:
        return ""

    variant_stubs: list[str] = []
    for variant_sym in group.variants:
        inner = _generate_overload_variant(variant_sym, group, ctx)
        if inner:
            variant_stubs.append(inner)

    return "\n\n".join(variant_stubs)


def _generate_overload_variant(sym: FunctionSymbol, group: OverloadGroup, ctx: StubContext) -> str:
    """Emit one ``@overload`` stub from the variant's own AST signature, else the live implementation."""
    is_async = sym.is_async
    if not is_async and group.live_func is not None:
        is_async = (
            inspect.iscoroutinefunction(group.live_func)
            or inspect.isasyncgenfunction(group.live_func)
        )
    keyword = "async def" if is_async else "def"

    raw_anns: dict[str, str] = sym.ast_info.raw_arg_annotations if sym.ast_info is not None else {}

    hints: dict = {}
    if sym.ast_info is not None and sym.ast_info.raw_params:
        params_with_hints = build_ast_only_params(sym.ast_info)
    elif group.live_func is not None:
        try:
            live_params = list(inspect.signature(group.live_func).parameters.values())
            hints = get_hints_for_method(group.live_func)
        except (ValueError, TypeError):
            live_params, hints = [], {}
        params_with_hints = [(p, hints) for p in live_params]
    else:
        params_with_hints = []

    params_with_hints = with_separators(params_with_hints)
    param_strs = render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx, raw_ann_override=raw_anns.get(raw_key(p)),
    ))

    ret_str = ""
    if sym.ast_info and sym.ast_info.raw_return_annotation:
        ret_str = sym.ast_info.raw_return_annotation
    elif hints:
        ret_str = annotation_to_str(hints.get("return", inspect.Parameter.empty), ctx)
    ret_part = f" -> {ret_str}" if ret_str else ""

    lines = ["@overload"]
    lines.extend(format_def("", keyword, sym.name, param_strs, ret_part, len(param_strs)))
    return "\n".join(lines)
