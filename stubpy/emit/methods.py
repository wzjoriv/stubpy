"""Method stubs: regular, class, static, abstract, async, property and cached-property methods."""
from __future__ import annotations

import functools
import inspect
from typing import Any

from stubpy._constants import KW_SEP_NAME, POS_SEP_NAME, PUBLIC_DUNDERS
from stubpy.analysis.docstrings import parse_docstring_types
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import DiagnosticStage
from stubpy.resolve import (
    get_hints_for_method,
    get_raw_params,
    resolve_params,
    signature_of,
    unwrap_callable,
    unwrap_descriptor,
)

from ._descriptors import find_property_mro, is_abstract_method, is_async_callable
from .annotations import annotation_to_str, format_param
from .decorators import decorator_base_name, stub_decorators
from .docstrings import make_docstring_body
from .signature import (
    format_def,
    infer_default_type,
    raw_key,
    render_params,
    warn_dynamic_kwargs,
    with_separators,
)

_SOURCE_ONLY_DECORATORS: frozenset[str] = frozenset({"final", "override", "deprecated"})


def methods_defined_on(cls: type) -> list[str]:
    """Return the names of callables defined directly on *cls* that belong in a stub.

    Dunders outside the public set and nested classes are skipped;
    definition order is kept.

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
    """Map each module-level function name in the symbol table to its AST info, cached per table."""
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


def _setter_signature(fset: Any, ctx: StubContext) -> str:
    """Return ``value: T`` for a property setter."""
    sig = signature_of(fset)
    val_params = [p for n, p in sig.parameters.items() if n not in ("self", "cls")] if sig else []
    val_name = val_params[0].name if val_params else "value"
    val_ann = get_hints_for_method(fset).get(
        val_name, val_params[0].annotation if val_params else inspect.Parameter.empty,
    )
    val_ann_str = annotation_to_str(val_ann, ctx)
    return f"{val_name}: {val_ann_str}" if val_ann_str else val_name


def _property_stub(cls: type, method_name: str, raw: property, ctx: StubContext,
                   indent: str, is_abstract: bool) -> str:
    """Emit ``@property`` plus ``@name.setter`` / ``@name.deleter`` found anywhere in the MRO."""
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
        lines.append(f"{indent}@{method_name}.setter")
        lines.append(f"{indent}def {method_name}(self, {_setter_signature(complete_prop.fset, ctx)}) -> None: ...")
    if complete_prop.fdel is not None:
        lines.append(f"{indent}@{method_name}.deleter")
        lines.append(f"{indent}def {method_name}(self) -> None: ...")
    return "\n".join(lines)


def _cached_property_stub(method_name: str, raw: functools.cached_property, ctx: StubContext,
                          indent: str) -> str:
    """Emit ``@cached_property`` with the wrapped function's return type."""
    ret_str = annotation_to_str(
        get_hints_for_method(raw.func).get("return", inspect.Parameter.empty), ctx,
    )
    ret_part = f" -> {ret_str}" if ret_str else ""
    return f"{indent}@cached_property\n{indent}def {method_name}(self){ret_part}: ..."


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


def _source_decorators(method_info: FunctionInfo | None, indent: str) -> list[str]:
    """Return ``final`` / ``override`` / ``deprecated`` decorator lines taken from the source."""
    if method_info is None:
        return []
    return [
        f"{indent}@{d}" for d in stub_decorators(method_info.decorators)
        if decorator_base_name(d) in _SOURCE_ONLY_DECORATORS
    ]


def generate_method_stub(
    cls: type,
    method_name: str,
    ctx: StubContext,
    indent: str = "    ",
    class_info: ClassInfo | None = None,
) -> str:
    """Return the stub line(s) for *method_name* in ``cls.__dict__``, or ``""`` if absent.

    Handles properties (with setters and deleters), cached properties,
    class / static / abstract / async methods, and resolves ``**kwargs`` /
    ``*args`` through the MRO.  Wrapped callables (``functools.wraps``,
    ``lru_cache``, JIT dispatchers) are unwrapped first.
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return ""

    if isinstance(raw, functools.cached_property):
        return _cached_property_stub(method_name, raw, ctx, indent)
    is_abstract = is_abstract_method(raw)
    if isinstance(raw, property):
        return _property_stub(cls, method_name, raw, ctx, indent, is_abstract)

    method_info = _method_ast_info(cls, method_name, ctx, class_info)
    is_new = method_name == "__new__"
    is_cls = isinstance(raw, classmethod) or is_new
    is_sta = isinstance(raw, staticmethod) and not is_new
    lines: list[str] = _source_decorators(method_info, indent)
    if is_cls and not is_new:
        lines.append(f"{indent}@classmethod")
    elif is_sta:
        lines.append(f"{indent}@staticmethod")
    if is_abstract:
        lines.append(f"{indent}@abstractmethod")

    keyword = "async def" if is_async_callable(raw) else "def"
    params_with_hints = _method_params(cls, method_name, ctx, method_info)
    warn_dynamic_kwargs(f"{cls.__name__}.{method_name}", params_with_hints, method_info, ctx)
    params_with_hints = with_separators(params_with_hints)

    ret_str = annotation_to_str(get_hints_for_method(raw).get("return", inspect.Parameter.empty), ctx)
    if not ret_str and method_name == "__init__":
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
        body = make_docstring_body(unwrap_callable(raw), indent + "    ")

    n_params = len([s for s in param_strs if s not in ("self", "cls")])
    lines.extend(format_def(indent, keyword, method_name, param_strs, ret_part, n_params, body))
    return "\n".join(lines)
