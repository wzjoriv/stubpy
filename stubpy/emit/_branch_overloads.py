"""
One ``@overload`` per branch of a literal dispatch that forwards ``**kwargs`` / ``*args`` to a different callee.
"""
from __future__ import annotations

import ast
import dataclasses
from collections.abc import Callable

from stubpy.analysis.harvest.models import BranchDispatch, FunctionInfo
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Stage
from stubpy.emit._constants import DISPATCH_LITERAL
from stubpy.resolve.static import ClassRef, FuncRef

from ._static import resolver_of

_Cases = tuple[tuple[tuple[str, ...], tuple[str, ...], bool], ...]


def _table_cases(dispatch: BranchDispatch, ctx: StubContext) -> _Cases:
    """The cases of a dispatch through a module-level dict, from its source or its live value."""
    module = ctx.source_module
    variables = module.symbols.variables if module is not None else []
    source = next((v.value_repr for v in reversed(variables) if v.name == dispatch.table and v.value_repr), None)
    try:
        node = ast.parse(source, mode="eval").body if source else None
    except SyntaxError:
        node = None
    if isinstance(node, ast.Dict):
        pairs = list(zip(node.keys, node.values, strict=True))
        if all(isinstance(k, (ast.Constant, ast.Attribute)) and isinstance(v, (ast.Name, ast.Attribute))
               for k, v in pairs):
            return tuple(((ast.unparse(k),), (ast.unparse(v),), dispatch.returned) for k, v in pairs)
        return ()
    live = ctx.module_namespace.get(dispatch.table or "")
    if not isinstance(live, dict):
        return ()
    cases = []
    for key, value in live.items():
        name = getattr(value, "__name__", None)
        if not isinstance(key, (str, int, bytes, bool)) or not name or ctx.module_namespace.get(name) is not value:
            return ()
        cases.append(((repr(key),), (name,), dispatch.returned))
    return tuple(cases)


def _cases(info: FunctionInfo, ctx: StubContext) -> _Cases:
    """The dispatch cases of *info* worth an ``@overload`` each; ``()`` without two distinct branches."""
    dispatch = info.dispatch
    if dispatch is None or info.hint_signature or info.hint_returns:
        return ()
    if not any(p.name == dispatch.selector and p.kind not in ("VAR_POSITIONAL", "VAR_KEYWORD")
               for p in info.raw_params):
        return ()
    cases = dispatch.cases if dispatch.table is None else _table_cases(dispatch, ctx)
    if dispatch.kind == "dict":
        annotation = info.raw_arg_annotations.get(dispatch.selector, "")
        enum_keys = all("." in lit and lit[:1].isidentifier() for lits, _, _ in cases for lit in lits)
        if DISPATCH_LITERAL not in annotation and not enum_keys:
            return ()
    return cases if len(cases) >= 2 or (cases and dispatch.callees - set(cases[0][1])) else ()


def _callee_return(callee: str, info: FunctionInfo, ctx: StubContext) -> str | None:
    """The type a call of *callee* returns, when it is a class or a same-module function with a return annotation."""
    if ctx.source_index is not None and ctx.source_module is not None:
        ref = resolver_of(ctx.source_index).names.dotted(ctx.source_module, callee, info)
        if isinstance(ref, ClassRef):
            return callee
        if isinstance(ref, FuncRef):
            ret = ref.info.raw_return_annotation
            return ret if ret and ref.module is ctx.source_module else None
    obj = ctx.module_namespace.get(callee.split(".")[0])
    for part in callee.split(".")[1:]:
        obj = getattr(obj, part, None)
    return callee if isinstance(obj, type) else None


def _variant(info: FunctionInfo, literals: tuple[str, ...], callees: tuple[str, ...], returned: bool,
             ctx: StubContext) -> FunctionInfo:
    """*info* as seen through one branch: only that branch's callees, the selector narrowed to its literals."""
    dispatch = info.dispatch
    others = dispatch.callees - set(callees)

    def keep(targets: list[str]) -> list[str]:
        return [t for t in targets if t not in others]

    kw_targets, pos_targets = keep(info.kwargs_forwarded_to), keep(info.args_forwarded_to)
    skips, explicit = dict(info.kwargs_positional_skips), dict(info.kwargs_explicit_names)
    if dispatch.kind == "dict":
        for callee in callees:
            kw_targets += [callee] if dispatch.forwards_kwargs and callee not in kw_targets else []
            pos_targets += [callee] if dispatch.forwards_args and callee not in pos_targets else []
            skips[callee] = dispatch.positional
            explicit[callee] = dispatch.explicit
    annotation = f"{DISPATCH_LITERAL}[{', '.join(literals)}]"
    ret = _callee_return(callees[0], info, ctx) if returned and len(callees) == 1 else None
    return dataclasses.replace(
        info, dispatch=None, selected=(dispatch.selector, annotation),
        raw_arg_annotations={**info.raw_arg_annotations, dispatch.selector: annotation},
        kwargs_forwarded_to=kw_targets, args_forwarded_to=pos_targets,
        kwargs_method_targets=keep(info.kwargs_method_targets), args_method_targets=keep(info.args_method_targets),
        kwargs_positional_skips=skips, kwargs_explicit_names=explicit,
        kwargs_dynamic=info.kwargs_dynamic and dispatch.kind != "dict", hint_returns=ret,
    )


def _overloaded(lines: list[str]) -> list[str]:
    """*lines* with ``@overload`` inserted above the decorators of the ``def`` line."""
    at = next((i for i, line in enumerate(lines) if line.lstrip().startswith(("def ", "async def "))), None)
    if at is None:
        return lines
    while at and lines[at - 1].lstrip().startswith("@"):
        at -= 1
    indent = lines[at][: len(lines[at]) - len(lines[at].lstrip())]
    return [*lines[:at], f"{indent}@overload", *lines[at:]]


def branch_overloads(info: FunctionInfo | None, ctx: StubContext,
                     emit: Callable[[FunctionInfo], list[str]]) -> list[str] | None:
    """The ``@overload`` variants of a function whose variadics go to a different callee per literal selector.

    One variant per branch narrows the selector to ``Literal[...]`` and takes
    that branch's callee parameters (and its return type when the branch
    returns the call); a last variant keeps the general signature.

    Parameters
    ----------
    info : FunctionInfo or None
        The harvested function.
    ctx : StubContext
        The current run context.
    emit : callable
        Renders one :class:`FunctionInfo` as stub lines, decorators included.

    Returns
    -------
    list of str or None
        The stub lines, or ``None`` when *info* has no literal dispatch.

    See Also
    --------
    forwarded_python_overloads : Variants copied from an ``@overload``-ed callee.

    Examples
    --------
    >>> branch_overloads(None, StubContext(), lambda info: []) is None
    True
    """
    cases = _cases(info, ctx) if info is not None else ()
    if not cases:
        return None
    blocks: list[list[str]] = []
    for literals, callees, returned in cases:
        block = _overloaded(emit(_variant(info, literals, callees, returned, ctx)))
        if block not in blocks:
            blocks.append(block)
    blocks.append(_overloaded(emit(dataclasses.replace(info, dispatch=None))))
    ctx.extra_imports.setdefault("overload", "from typing import overload")
    ctx.extra_imports.setdefault(DISPATCH_LITERAL, f"from typing import {DISPATCH_LITERAL}")
    ctx.diagnostics.info(Stage.RESOLVE, info.name, f"forwards to a different callee per value of "
                         f"{info.dispatch.selector!r}; emitted {len(blocks)} @overload variants")
    return [line for block in blocks for line in block]
