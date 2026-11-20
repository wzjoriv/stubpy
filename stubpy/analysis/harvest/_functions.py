"""
Harvest one function definition into a :class:`FunctionInfo`.
"""
from __future__ import annotations

import ast

from ._branches import scan_dispatch
from ._calls import scan_forwarding
from ._hints import HintNames, split_hints
from ._inferred_returns import inferred_return
from ._local_imports import scan_local_imports
from ._nodes import children, decorator_name, is_stub_body, type_params, unparse
from ._params import build_raw_params, collect_annotations, infer_default_types
from ._reads import scan_reads
from ._returns import structural_return
from .models import FunctionInfo

_OVERLOAD_NAMES: frozenset[str] = frozenset({"overload"})


def harvest_function_node(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    hint_names: HintNames | None = None,
    is_async: bool | None = None,
) -> FunctionInfo:
    """Build a :class:`FunctionInfo`, including its variadic forwarding targets."""
    is_async_generator = isinstance(node, ast.AsyncFunctionDef) and _yields(node)
    if is_async is None:
        is_async = isinstance(node, ast.AsyncFunctionDef)
    is_async = is_async and not is_async_generator

    decorator_nodes, hints = split_hints(node.decorator_list, hint_names or HintNames())
    decorators = [d for d in (unparse(d) for d in decorator_nodes) if d]
    decorator_names = [decorator_name(d) for d in decorator_nodes]
    annotations = collect_annotations(node)
    inferred = infer_default_types(node, annotations)
    forwarding = scan_forwarding(node, hint_names.copiers if hint_names is not None else None)
    returned, returned_class = inferred_return(node)
    kwargs_read, args_read = scan_reads(node, set(forwarding.kw_consumed) | forwarding.kw_injected)

    return FunctionInfo(
        name=node.name,
        lineno=node.lineno,
        is_async=is_async,
        is_async_generator=is_async_generator,
        decorators=decorators,
        is_overload=any(n in _OVERLOAD_NAMES for n in decorator_names),
        raw_arg_annotations=annotations,
        raw_return_annotation=unparse(node.returns),
        kwargs_forwarded_to=forwarding.kw_targets,
        args_forwarded_to=forwarding.pos_targets,
        kwargs_positional_skips=forwarding.kw_positional_skips,
        kwargs_explicit_names={k: frozenset(v) for k, v in forwarding.kw_explicit_names.items()},
        kwargs_method_targets=forwarding.kw_method_targets,
        args_method_targets=forwarding.args_method_targets,
        kwargs_unknown_starred=forwarding.kw_unknown_starred,
        kwargs_consumed=forwarding.kw_consumed,
        kwargs_injected=forwarding.kw_injected,
        kwargs_dynamic=forwarding.kw_dynamic,
        kwargs_read=kwargs_read,
        args_read=args_read,
        dispatch=scan_dispatch(node),
        local_imports=scan_local_imports(node) if forwarding.kw_targets + forwarding.pos_targets else {},
        is_stub_body=is_stub_body(node.body),
        raw_arg_inferred_types=inferred,
        raw_inferred_return=returned,
        inferred_return_class=returned_class,
        structural_return=structural_return(node),
        raw_params=build_raw_params(node, annotations, inferred),
        hint_signature=hints.signature,
        hint_returns=hints.returns,
        hint_ignore=hints.ignore,
        type_params=type_params(node),
    )


def _yields(node: ast.AsyncFunctionDef) -> bool:
    """Return ``True`` when *node*'s own body (not a nested scope) contains ``yield``."""
    stack: list[ast.AST] = list(node.body)
    while stack:
        sub = stack.pop()
        if isinstance(sub, (ast.Yield, ast.YieldFrom)):
            return True
        if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(children(sub))
    return False


def harvest_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    """Return the :class:`FunctionInfo` of one function definition node."""
    return harvest_function_node(node)
