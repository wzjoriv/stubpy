"""
AST-only emission: signatures and class stubs synthesised without a live module.
"""
from __future__ import annotations

import dataclasses

from stubpy._constants import PUBLIC_DUNDERS
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.core.context import StubContext
from stubpy.emit._constants import ASYNC_ITERATOR_RETURN, IMPLICIT_CLASSMETHODS

from ._ast_attributes import attribute_lines
from ._ast_branches import branch_groups, branch_lines, unbranched
from ._ast_params import params_from_raw
from ._attrs import attrs_field_lines, attrs_init_lines
from ._branch_overloads import branch_overloads
from ._def_layout import format_def, hinted_def
from ._dunders import dunder_param_types, dunder_return
from ._inherited_property import inherited_accessor
from ._instance_attrs import declared_names, source_attribute_lines
from ._overload_forward import forwarded_python_overloads
from ._reads import with_reads
from ._static import static_params
from ._variadic_notes import warn_dynamic_kwargs
from .annotations import format_param
from .annotations.params import raw_key
from .annotations.style import style_text
from .branches import Unit
from .decorators import decorator_base_name, stub_decorators
from .docstrings import docstring_block
from .signature import generic_name, receiver_text, render_params, structural_return, with_separators


def _swapped(owner: ClassInfo | None, old: FunctionInfo, new: FunctionInfo) -> ClassInfo | None:
    """*owner* with method *old* replaced by *new*, so source resolution finds the variant."""
    if owner is None:
        return None
    return dataclasses.replace(owner, methods=[new if m is old else m for m in owner.methods])


def emit_method_from_ast(minfo: FunctionInfo, ctx: StubContext, indent: str = "    ",
                         owner: ClassInfo | None = None) -> list[str]:
    """Return the stub lines of a method from its AST info.

    Only stub-relevant decorators are kept. With its *owner* class,
    variadics are resolved from source when the module was not imported.

    Parameters
    ----------
    minfo : FunctionInfo
        The method's AST info.
    ctx : StubContext
        The current run context.
    indent : str, optional
        The indentation of the stub lines. Defaults to four spaces.
    owner : ClassInfo, optional
        The class owning the method. Defaults to None.

    Returns
    -------
    list of str
        The stub lines.

    See Also
    --------
    emit_class_from_ast : Emits a whole class.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> method = ast_harvest("class A:\\n    def f(self, x: int) -> str: ...").classes[0].methods[0]
    >>> emit_method_from_ast(method, StubContext())
    ['    def f(self, x: int) -> str: ...']
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
    branched = branch_overloads(minfo, ctx, lambda info: emit_method_from_ast(
        info, ctx, indent, _swapped(owner, minfo, info)))
    if branched is not None:
        return branched

    raw_anns = minfo.raw_arg_annotations or {}
    inferred = getattr(minfo, "raw_arg_inferred_types", {}) or {}
    ret_str = minfo.hint_returns or style_text(minfo.raw_return_annotation, ctx) or (
        structural_return(minfo) or (ASYNC_ITERATOR_RETURN if minfo.is_async_generator else "")
    ) or (dunder_return(minfo.name) if owner is not None else "")

    raw_params = list(minfo.raw_params)
    receiver = ""
    if not is_sta and raw_params and raw_params[0].kind in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"):
        receiver = raw_anns.get(raw_params[0].name) or ""
        raw_params = raw_params[1:]
    resolved = static_params(minfo, ctx, owner) if owner is not None else None
    if resolved is not None:
        warn_dynamic_kwargs(f"{owner.name}.{minfo.name}", resolved, minfo, ctx)
    params_with_hints = with_separators(with_reads(
        resolved if resolved is not None else params_from_raw(raw_params, skip_receiver_names=False), minfo,
    ))
    self_prefix = [] if is_sta else [receiver_text("cls" if is_cls else "self", receiver)]
    protocol = dunder_param_types(minfo.name, [p for p, _ in params_with_hints]) if owner is not None else {}
    param_strs = self_prefix + render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx,
        raw_ann_override=raw_anns.get(raw_key(p)),
        inferred_type=inferred.get(p.name) or protocol.get(p.name),
    ))
    ret_part = f" -> {ret_str}" if ret_str else ""

    n_params = len(param_strs) - len(self_prefix)
    lines.extend(format_def(indent, keyword, generic_name(minfo.name, minfo), param_strs, ret_part, n_params, body))
    return lines


def keeps_method(name: str, ctx: StubContext) -> bool:
    """Return whether a method belongs in a stub.

    Public dunders are kept; private names only when ``include_private`` is set.

    Parameters
    ----------
    name : str
        The method name.
    ctx : StubContext
        The current run context.

    Returns
    -------
    bool
        True when the method is kept.

    Examples
    --------
    >>> keeps_method("__init__", StubContext()), keeps_method("_helper", StubContext())
    (True, False)
    """
    if name.startswith("__") and name.endswith("__"):
        return name in PUBLIC_DUNDERS
    return not name.startswith("_") or ctx.config.include_private


def method_lines(ci: ClassInfo, ctx: StubContext, indent: str, owner: ClassInfo | None = None) -> list[str]:
    """Return the stub lines of a class's methods.

    An implementation that has ``@overload`` variants is dropped, and
    duplicate variants are written once.

    Parameters
    ----------
    ci : ClassInfo
        The class whose methods are emitted.
    ctx : StubContext
        The current run context.
    indent : str
        The indentation of the stub lines.
    owner : ClassInfo, optional
        The class used to resolve variadics. Defaults to *ci*.

    Returns
    -------
    list of str
        The stub lines.

    See Also
    --------
    emit_method_from_ast : Emits one method.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> ci = ast_harvest("class A:\\n    def f(self): ...\\n    def _g(self): ...").classes[0]
    >>> method_lines(ci, StubContext(), "")
    ['def f(self): ...']
    """
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


def _nested_lines(ci: ClassInfo, ctx: StubContext, indent: str) -> list[str]:
    return [
        emit_class_from_ast(nested, ctx, indent) for nested in ci.classes
        if not nested.hint_ignore and (ctx.config.include_private or not nested.name.startswith("_"))
    ]


def member_text(group: ClassInfo, ctx: StubContext) -> str:
    """Return the unindented stubs of one branch's members.

    Attributes come first, then nested classes, then methods.

    Parameters
    ----------
    group : ClassInfo
        A class holding one branch's members, from :func:`branch_groups`.
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        The members' stub text.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> ci = ast_harvest("class A:\\n    x: int\\n    def f(self): ...").classes[0]
    >>> print(member_text(ci, StubContext()))
    x: int
    <BLANKLINE>
    def f(self): ...
    """
    lines = attribute_lines(group, ctx, "") + _nested_lines(group, ctx, "")
    methods = method_lines(group, ctx, "")
    return "\n".join(lines + ([""] if lines and methods else []) + methods)


def emit_class_from_ast(ci: ClassInfo, ctx: StubContext, indent: str = "") -> str:
    """Return a class stub built from AST info alone.

    Contains decorators, bases, attributes, nested classes and methods;
    members inside version branches follow, wrapped in their ``if`` blocks.

    Parameters
    ----------
    ci : ClassInfo
        The class's AST info.
    ctx : StubContext
        The current run context.
    indent : str, optional
        The indentation of the ``class`` line. Defaults to ``""``.

    Returns
    -------
    str
        The class stub, without a trailing newline.

    See Also
    --------
    emit_method_from_ast : Emits one method.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> ci = ast_harvest("class A:\\n    x: int\\n    def f(self) -> str: ...").classes[0]
    >>> print(emit_class_from_ast(ci, StubContext()))
    class A:
        x: int
    <BLANKLINE>
        def f(self) -> str: ...
    """
    groups = branch_groups(ci)
    ci = unbranched(ci) if groups else ci
    base_str = f"({', '.join(ci.bases)})" if ci.bases else ""
    lines: list[str] = [f"{indent}@{d}" for d in stub_decorators(ci.decorators)]
    lines.append(f"{indent}class {generic_name(ci.name, ci)}{base_str}:")
    inner = indent + "    "

    body = attribute_lines(ci, ctx, inner)
    body += attrs_field_lines(ci, ctx, inner, declared_names(body, ci))
    body += source_attribute_lines(ci, declared_names(body, ci), ctx, inner)
    if ctx.config.include_docstrings and ci.docstring and ci.docstring.strip():
        doc = docstring_block(ci.docstring, inner)
        body.insert(0, f"{inner}{doc}")
        if len(body) > 1:
            body.insert(1, "")
    body.extend(_nested_lines(ci, ctx, inner))
    methods = attrs_init_lines(ci, ctx, inner) + method_lines(ci, ctx, inner)
    if body and methods:
        body.append("")
    body.extend(methods)
    blocks = branch_lines([Unit(member_text(g, ctx), False, path) for path, g in groups], inner)
    if body and blocks:
        body.append("")
    body.extend(blocks)
    lines.extend(body or [f"{inner}..."])
    return "\n".join(lines)
