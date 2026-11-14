"""Method stubs: regular, class, static, abstract, async and property methods."""
from __future__ import annotations

import inspect
from typing import Any

from stubpy._constants import KW_SEP_NAME, POS_SEP_NAME, PUBLIC_DUNDERS
from stubpy.analysis.docstrings import parse_docstring_types
from stubpy.analysis.harvest.models import FunctionInfo
from stubpy.analysis.symbols.models import FunctionSymbol
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import DiagnosticStage
from stubpy.resolve import get_hints_for_method, get_raw_params, resolve_params, unwrap_descriptor

from ._descriptors import find_property_mro, is_abstract_method, is_async_callable
from .annotations import annotation_to_str, format_param
from .docstrings import make_docstring_body
from .signature import format_def, infer_default_type, raw_key, render_params, with_separators


def methods_defined_on(cls: type) -> list[str]:
    """Return the names of callables defined directly on *cls* that belong in a stub.

    Dunders outside the public set are skipped; definition order is kept.

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
        if callable(obj) or isinstance(obj, (classmethod, staticmethod, property)):
            names.append(name)
    return names


def function_ast_infos(ctx: StubContext) -> dict[str, FunctionInfo]:
    """Map each module-level function name in the symbol table to its AST info."""
    by_name: dict[str, FunctionInfo] = {}
    if ctx.symbol_table is not None:
        for s in ctx.symbol_table:
            if isinstance(s, FunctionSymbol) and s.ast_info is not None:
                by_name[s.name] = s.ast_info
    return by_name


def _method_ast_info(cls: type, method_name: str, ctx: StubContext) -> FunctionInfo | None:
    """Return the AST info of *method_name* on *cls* from the symbol table, if any."""
    if ctx.symbol_table is None:
        return None
    try:
        cls_sym = ctx.symbol_table.get_class(cls.__name__)
        if cls_sym is not None and cls_sym.ast_info is not None:
            for minfo in cls_sym.ast_info.methods:
                if minfo.name == method_name:
                    return minfo
    except Exception:
        pass
    return None


def _property_stub(cls: type, method_name: str, raw: property, ctx: StubContext,
                   indent: str, is_abstract: bool) -> str:
    """Emit ``@property`` and, when a setter exists anywhere in the MRO, ``@name.setter``."""
    complete_prop = find_property_mro(cls, method_name) or raw

    hints = get_hints_for_method(complete_prop.fget)
    ret_str = annotation_to_str(hints.get("return", inspect.Parameter.empty), ctx)
    ret_part = f" -> {ret_str}" if ret_str else ""

    lines: list[str] = []
    if is_abstract:
        lines.append(f"{indent}@abstractmethod")
    lines.append(f"{indent}@property")
    lines.append(f"{indent}def {method_name}(self){ret_part}: ...")

    if complete_prop.fset is not None:
        setter_hints = get_hints_for_method(complete_prop.fset)
        try:
            val_params = [
                p for n, p in inspect.signature(complete_prop.fset).parameters.items()
                if n not in ("self", "cls")
            ]
        except (ValueError, TypeError):
            val_params = []

        val_name = val_params[0].name if val_params else "value"
        val_ann = setter_hints.get(
            val_name,
            val_params[0].annotation if val_params else inspect.Parameter.empty,
        )
        val_ann_str = annotation_to_str(val_ann, ctx)
        val_sig = f"{val_name}: {val_ann_str}" if val_ann_str else val_name

        lines.append(f"{indent}@{method_name}.setter")
        lines.append(f"{indent}def {method_name}(self, {val_sig}) -> None: ...")

    return "\n".join(lines)


def _method_params(cls: type, method_name: str, ctx: StubContext,
                   method_info: FunctionInfo | None) -> list[tuple[inspect.Parameter, dict[str, Any]]]:
    """Return the method's params, resolving variadics unless the config disables it."""
    if getattr(ctx.config, "resolve_kwargs", True) and getattr(ctx.config, "resolve_args", True):
        return resolve_params(
            cls, method_name,
            ast_info=method_info,
            namespace=ctx.module_namespace,
            ast_info_by_name=function_ast_infos(ctx),
        )
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
                DiagnosticStage.EMIT,
                f"{cls.__name__}.{method_name}",
                f"Parameter {p.name!r} has no annotation and no inferrable type; "
                "stub will emit bare name.",
            )


def generate_method_stub(
    cls: type,
    method_name: str,
    ctx: StubContext,
    indent: str = "    ",
) -> str:
    """Return the stub line(s) for *method_name* in ``cls.__dict__``, or ``""`` if absent.

    Handles properties (with setters), class / static / abstract / async
    methods, and resolves ``**kwargs`` / ``*args`` through the MRO.
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return ""

    is_abstract = is_abstract_method(raw)
    if isinstance(raw, property):
        return _property_stub(cls, method_name, raw, ctx, indent, is_abstract)

    is_cls = isinstance(raw, classmethod)
    is_sta = isinstance(raw, staticmethod)
    lines: list[str] = []
    if is_cls:
        lines.append(f"{indent}@classmethod")
    elif is_sta:
        lines.append(f"{indent}@staticmethod")
    if is_abstract:
        lines.append(f"{indent}@abstractmethod")

    keyword = "async def" if is_async_callable(raw) else "def"
    method_info = _method_ast_info(cls, method_name, ctx)
    params_with_hints = with_separators(_method_params(cls, method_name, ctx, method_info))

    ret_str = annotation_to_str(get_hints_for_method(raw).get("return", inspect.Parameter.empty), ctx)
    if not ret_str and method_name in ("__init__", "__new__"):
        ret_str = "None"

    raw_anns = method_info.raw_arg_annotations if method_info is not None else {}

    ds_types: dict[str, str] = {}
    if getattr(ctx.config, "infer_types_from_docstrings", False):
        fn_for_doc = unwrap_descriptor(raw)
        doc = getattr(fn_for_doc, "__doc__", None) if fn_for_doc else None
        if doc:
            ds_types = parse_docstring_types(doc).params

    _note_unannotated(cls, method_name, params_with_hints, raw_anns, ds_types, ctx)

    self_prefix = [] if is_sta else (["cls"] if is_cls else ["self"])
    param_strs = self_prefix + render_params(params_with_hints, lambda p, h: format_param(
        p, h, ctx,
        raw_ann_override=raw_anns.get(raw_key(p)),
        docstring_type=ds_types.get(p.name) if ds_types else None,
        inferred_type=infer_default_type(p, ds_types),
    ))
    ret_part = f" -> {ret_str}" if ret_str else ""

    body = "..."
    if getattr(ctx.config, "include_docstrings", False):
        fn = raw.__func__ if isinstance(raw, (classmethod, staticmethod)) else raw
        body = make_docstring_body(fn, indent + "    ")

    n_params = len([s for s in param_strs if s not in ("self", "cls")])
    lines.extend(format_def(indent, keyword, method_name, param_strs, ret_part, n_params, body))
    return "\n".join(lines)
