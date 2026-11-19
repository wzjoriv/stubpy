"""
Method stubs: regular, class, static, abstract, async, property and cached-property methods.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any

from stubpy._constants import (
    ASYNC_ITERATOR_RETURN,
    IMPLICIT_CLASSMETHODS,
    KW_SEP_NAME,
    METHOD_INNER_DECORATORS,
    METHOD_OUTER_DECORATORS,
    POS_SEP_NAME,
    PUBLIC_DUNDERS,
)
from stubpy.analysis.docstrings import parse_docstring_types
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.analysis.hints import is_ignored, returns_hint, signature_hint
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Stage
from stubpy.resolve import (
    get_hints_for_method,
    get_raw_params,
    resolve_params,
    signature_of,
    unwrap_callable,
    unwrap_descriptor,
)

from ._descriptors import find_property_mro, is_abstract_method, is_async_callable, is_async_generator
from ._forwarded import forwarded_overloads
from ._overload_forward import forwarded_python_overloads
from ._static import refine_live
from .annotations import annotation_to_str, format_param
from .annotations.params import raw_key
from .annotations.source import hint_text
from .decorators import decorator_base_name, stub_decorators
from .docstrings import make_docstring_body
from .signature import (
    format_def,
    forwarding_callees,
    generic_name,
    hinted_def,
    infer_default_type,
    note_compiled_overloads,
    receiver_text,
    render_params,
    structural_return,
    warn_dynamic_kwargs,
    with_separators,
)


def methods_defined_on(cls: type) -> list[str]:
    """Return the names of callables defined directly on a class that belong in a stub.

    Dunders outside the public set and nested classes are skipped;
    definition order is kept.

    Parameters
    ----------
    cls : type
        The class.

    Returns
    -------
    list of str
        The member names, in definition order.

    See Also
    --------
    generate_method_stub : Emits the stub for one name.

    Examples
    --------
    >>> class Parent:
    ...     def parent_method(self) -> None: ...
    >>> class Child(Parent):
    ...     def child_method(self) -> None: ...
    >>> methods_defined_on(Child)
    ['child_method']
    """
    names: list[str] = []
    for name, obj in cls.__dict__.items():
        if name.startswith("__") and name.endswith("__") and name not in PUBLIC_DUNDERS:
            continue
        if isinstance(obj, type):
            continue
        if callable(obj) or isinstance(obj, (classmethod, staticmethod, property, functools.cached_property)):
            names.append(name)
    return names


def function_ast_infos(ctx: StubContext) -> dict[str, FunctionInfo]:
    """Map each module-level function name in the symbol table to its AST info.

    The mapping is cached per table.

    Parameters
    ----------
    ctx : StubContext
        The current run context.

    Returns
    -------
    dict of str to FunctionInfo
        The infos by name; empty without a symbol table.

    Examples
    --------
    >>> function_ast_infos(StubContext())
    {}
    """
    if ctx.symbol_table is None:
        return {}
    return ctx.symbol_table.function_infos()


def _method_ast_info(
    cls: type, method_name: str, ctx: StubContext, class_info: ClassInfo | None = None,
) -> FunctionInfo | None:
    """Return the AST info of *method_name* on *cls*, from *class_info* or the symbol table."""
    if class_info is None and ctx.symbol_table is not None:
        cls_sym = ctx.symbol_table.get_class(cls.__name__)
        class_info = cls_sym.ast_info if cls_sym is not None else None
    if class_info is None:
        return None
    found = [m for m in class_info.methods if m.name == method_name and not m.is_overload]
    return found[-1] if found else None


def _class_info(cls: type, ctx: StubContext) -> ClassInfo | None:
    """Return the AST info of *cls* from the symbol table."""
    sym = ctx.symbol_table.get_class(cls.__name__) if ctx.symbol_table is not None else None
    return sym.ast_info if sym is not None else None


def _setter_signature(fset: Any, ctx: StubContext) -> str:
    """Return ``value: T`` for a property setter."""
    sig = signature_of(fset)
    val_params = [p for n, p in sig.parameters.items() if n not in ("self", "cls")] if sig else []
    val_name = val_params[0].name if val_params else "value"
    val_ann_str = hint_text(fset, val_name, ctx) if val_params else ""
    return f"{val_name}: {val_ann_str}" if val_ann_str else val_name


def _property_stub(cls: type, method_name: str, raw: property, ctx: StubContext,
                   indent: str, is_abstract: bool) -> str:
    """Emit ``@property`` plus ``@name.setter`` / ``@name.deleter`` found anywhere in the MRO."""
    complete_prop = find_property_mro(cls, method_name) or raw

    ret_str = hint_text(complete_prop.fget, "return", ctx) if complete_prop.fget is not None else ""
    ret_part = f" -> {ret_str}" if ret_str else ""

    lines: list[str] = []
    if is_abstract:
        lines.append(f"{indent}@abstractmethod")
    lines.append(f"{indent}@property")
    lines.append(f"{indent}def {method_name}(self){ret_part}: ...")

    if complete_prop.fset is not None:
        lines.append(f"{indent}@{method_name}.setter")
        lines.append(f"{indent}def {method_name}(self, {_setter_signature(complete_prop.fset, ctx)}) -> None: ...")
    if complete_prop.fdel is not None:
        lines.append(f"{indent}@{method_name}.deleter")
        lines.append(f"{indent}def {method_name}(self) -> None: ...")
    return "\n".join(lines)


def _cached_property_stub(method_name: str, raw: functools.cached_property, ctx: StubContext,
                          indent: str) -> str:
    """Emit ``@cached_property`` with the wrapped function's return type."""
    ret_str = hint_text(raw.func, "return", ctx)
    ret_part = f" -> {ret_str}" if ret_str else ""
    return f"{indent}@cached_property\n{indent}def {method_name}(self){ret_part}: ..."


def _method_params(cls: type, method_name: str, ctx: StubContext,
                   method_info: FunctionInfo | None) -> list[tuple[inspect.Parameter, dict[str, Any]]]:
    """Return the method's params, resolving variadics unless the config disables it."""
    if getattr(ctx.config, "resolve_kwargs", True) and getattr(ctx.config, "resolve_args", True):
        params = resolve_params(
            cls, method_name,
            ast_info=method_info,
            namespace=ctx.module_namespace,
            ast_info_by_name=function_ast_infos(ctx),
        )
        owner = _class_info(cls, ctx)
        return refine_live(params, method_info, ctx, owner) if owner is not None else params
    own_raw, own_hints = get_raw_params(cls, method_name)
    if own_raw is None:
        return []
    return [(p, own_hints) for p in own_raw]


def _note_unannotated(cls: type, method_name: str, params_with_hints: list, raw_anns: dict[str, str],
                      ds_types: dict[str, str], ctx: StubContext) -> None:
    """Record an INFO diagnostic for each parameter left without any type."""
    for p, h in params_with_hints:
        if p.name in (KW_SEP_NAME, POS_SEP_NAME, "self", "cls"):
            continue
        if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        has_ann = (
            h.get(p.name) not in (None, inspect.Parameter.empty)
            or p.annotation is not inspect.Parameter.empty
            or raw_anns.get(raw_key(p))
            or (ds_types and p.name in ds_types)
            or infer_default_type(p, ds_types) is not None
        )
        if not has_ann:
            ctx.diagnostics.info(
                Stage.EMIT,
                f"{cls.__name__}.{method_name}",
                f"Parameter {p.name!r} has no annotation and no inferrable type; "
                "stub will emit bare name.",
            )


def _source_decorators(method_info: FunctionInfo | None, indent: str, kinds: frozenset[str]) -> list[str]:
    """Return the decorator lines of the given *kinds* taken from the source, in source order."""
    if method_info is None:
        return []
    return [f"{indent}@{d}" for d in stub_decorators(method_info.decorators) if decorator_base_name(d) in kinds]


def _receiver(raw: Any, method_info: FunctionInfo | None, default: str, ctx: StubContext) -> str:
    """Return ``self`` / ``cls``, annotated when the source annotates the receiver (``self: E``)."""
    sig = signature_of(unwrap_descriptor(raw))
    params = list(sig.parameters.values()) if sig is not None else []
    if not params or params[0].kind not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
        return default
    first = params[0]
    text = (method_info.raw_arg_annotations.get(first.name) if method_info is not None else None) or ""
    if not text and first.annotation is not inspect.Parameter.empty:
        text = annotation_to_str(get_hints_for_method(raw).get(first.name, first.annotation), ctx)
    return receiver_text(default, text)


def generate_method_stub(
    cls: type,
    method_name: str,
    ctx: StubContext,
    indent: str = "    ",
    class_info: ClassInfo | None = None,
) -> str:
    """Return the stub line(s) for a method defined directly on a class.

    Handles properties (with setters and deleters), cached properties,
    class / static / abstract / async methods, and resolves ``**kwargs`` /
    ``*args`` through the MRO. Wrapped callables (``functools.wraps``,
    ``lru_cache``, JIT dispatchers) are unwrapped first.

    Parameters
    ----------
    cls : type
        The class.
    method_name : str
        The attribute name, looked up in ``cls.__dict__``.
    ctx : StubContext
        The current run context.
    indent : str, optional
        The indentation of the stub lines. Defaults to four spaces.
    class_info : ClassInfo, optional
        The class's AST info; looked up in the symbol table when omitted. Defaults to None.

    Returns
    -------
    str
        The stub text, or ``""`` when the class does not define the name or it is ignored.

    See Also
    --------
    methods_defined_on : Lists the names to pass.
    generate_function_stub : The equivalent for module-level functions.

    Examples
    --------
    >>> class Point:
    ...     def scale(self, factor: float) -> "Point": ...
    >>> generate_method_stub(Point, "scale", StubContext())
    '    def scale(self, factor: float) -> Point: ...'
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return ""
    method_info = _method_ast_info(cls, method_name, ctx, class_info)
    if is_ignored(raw, method_info):
        return ""

    if isinstance(raw, functools.cached_property):
        return _cached_property_stub(method_name, raw, ctx, indent)
    is_abstract = is_abstract_method(raw)
    if isinstance(raw, property):
        return _property_stub(cls, method_name, raw, ctx, indent, is_abstract)

    implicit = method_name in IMPLICIT_CLASSMETHODS
    is_cls = isinstance(raw, classmethod) or implicit
    is_sta = isinstance(raw, staticmethod) and not implicit
    lines: list[str] = _source_decorators(method_info, indent, METHOD_OUTER_DECORATORS)
    if is_cls and not implicit:
        lines.append(f"{indent}@classmethod")
    elif is_sta:
        lines.append(f"{indent}@staticmethod")
    if is_abstract:
        lines.append(f"{indent}@abstractmethod")
    lines.extend(_source_decorators(method_info, indent, METHOD_INNER_DECORATORS))

    is_agen = is_async_generator(raw)
    keyword = "async def" if is_async_callable(raw) else "def"
    body = "..."
    if getattr(ctx.config, "include_docstrings", False):
        body = make_docstring_body(unwrap_callable(raw), indent + "    ")
    sig_text = signature_hint(raw, method_info)
    hinted = hinted_def(indent, keyword, method_name, sig_text, ctx, body) if sig_text else None
    if hinted is not None:
        return "\n".join(lines + hinted)

    forwarded = forwarded_overloads(cls, method_name, method_info, ctx, indent)
    if forwarded is not None:
        return "\n".join(lines + forwarded)
    owner_info = class_info if class_info is not None else _class_info(cls, ctx)
    if not is_sta and owner_info is not None:
        receiver = "cls" if is_cls else "self"
        py_overloads = forwarded_python_overloads(method_info, ctx, indent, owner_info, receiver, keyword)
        if py_overloads is not None:
            return "\n".join(lines + py_overloads)

    params_with_hints = _method_params(cls, method_name, ctx, method_info)
    warn_dynamic_kwargs(f"{cls.__name__}.{method_name}", params_with_hints, method_info, ctx)
    note_compiled_overloads(
        f"{cls.__name__}.{method_name}", params_with_hints,
        forwarding_callees(method_info, ctx.module_namespace, cls, method_name), ctx,
    )
    params_with_hints = with_separators(params_with_hints)

    ret_str = hint_text(raw, "return", ctx)
    if not ret_str and method_name == "__init__":
        ret_str = "None"
    ret_str = returns_hint(raw, method_info) or ret_str or structural_return(method_info) or (
        ASYNC_ITERATOR_RETURN if is_agen else ""
    )

    raw_anns = method_info.raw_arg_annotations if method_info is not None else {}

    ds_types: dict[str, str] = {}
    if getattr(ctx.config, "infer_types", False):
        fn_for_doc = unwrap_descriptor(raw)
        doc = getattr(fn_for_doc, "__doc__", None) if fn_for_doc else None
        if doc:
            ds_types = parse_docstring_types(doc).params

    _note_unannotated(cls, method_name, params_with_hints, raw_anns, ds_types, ctx)

    self_prefix = [] if is_sta else [_receiver(raw, method_info, "cls" if is_cls else "self", ctx)]
    param_strs = self_prefix + render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx,
        raw_ann_override=raw_anns.get(raw_key(p)),
        docstring_type=ds_types.get(p.name) if ds_types else None,
        inferred_type=infer_default_type(p, ds_types),
    ))
    ret_part = f" -> {ret_str}" if ret_str else ""
    n_params = len(param_strs) - len(self_prefix)
    lines.extend(format_def(indent, keyword, generic_name(method_name, method_info), param_strs, ret_part, n_params, body))
    return "\n".join(lines)
