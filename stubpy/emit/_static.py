"""AST-mode back-tracing: resolve variadics from source and import the names foreign parameters use."""
from __future__ import annotations

import ast
import builtins
import inspect

from stubpy._constants import TYPING_BACKPORTS, TYPING_CANDIDATES
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo, NonLiteralDefault
from stubpy.analysis.origins import relative_module
from stubpy.core.context import StubContext
from stubpy.resolve import ParamWithHints
from stubpy.resolve.static import (
    ClassRef,
    FuncRef,
    PartialRef,
    SourceHints,
    SourceIndex,
    SourceModule,
    StaticResolver,
)

_ELLIPSIS = NonLiteralDefault("...")


def static_params(info: FunctionInfo, ctx: StubContext, owner: ClassInfo | None = None) -> list[ParamWithHints] | None:
    """Return *info*'s parameters with ``*args`` / ``**kwargs`` resolved from source, or ``None`` when not applicable.

    Applies in AST mode (no live module) when the function forwards a variadic.
    """
    module = ctx.source_module
    index = ctx.source_index
    if module is None or index is None or ctx.module_namespace or not (
        ctx.config.resolve_kwargs and ctx.config.resolve_args
    ):
        return None
    if not any(p.kind in ("VAR_POSITIONAL", "VAR_KEYWORD") for p in info.raw_params):
        return None
    resolver = resolver_of(index)
    if owner is None:
        params = resolver.function(FuncRef(module, info))
    else:
        cref = ClassRef(module, owner)
        if info.is_overload or not any(m is info for m in owner.methods):
            return None
        params = resolver.method(cref, info.name)
    if params is None:
        return None
    return [bind_foreign(p, h, ctx) for p, h in params]


def resolver_of(index: SourceIndex) -> StaticResolver:
    if index.resolver is None:
        index.resolver = StaticResolver(index)
    return index.resolver


def static_partial(value_repr: str, ctx: StubContext) -> tuple[list[ParamWithHints], str] | None:
    """Return the open parameters and return type of ``partial(target, ...)`` resolved from source."""
    module, index = ctx.source_module, ctx.source_index
    if module is None or index is None or ctx.module_namespace:
        return None
    resolver = resolver_of(index)
    ref = resolver.names.expression(module, value_repr, None)
    if not isinstance(ref, PartialRef):
        return None
    params = resolver.of_ref(ref, frozenset())
    if params is None:
        return None
    target = ref.target
    ret = ""
    if isinstance(target, ClassRef):
        ret = target.info.name if bind_names([target.info.name], target.module, ctx) else ""
    elif isinstance(target, FuncRef) and target.info.raw_return_annotation:
        names = names_in(target.info.raw_return_annotation)
        if names is not None and (target.module is module or bind_names(names, target.module, ctx)):
            ret = target.info.raw_return_annotation
    return [bind_foreign(p, h, ctx) for p, h in params], ret


def names_in(text: str) -> list[str] | None:
    """Return the names an expression uses, or ``None`` when it does not parse."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    return [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]


def _local_names(module: SourceModule) -> set[str]:
    sym = module.symbols
    return (
        {c.name for c in sym.classes} | {f.name for f in sym.functions} | {v.name for v in sym.variables}
        | {t.name for t in sym.typevar_decls} | {i.local for i in sym.imports}
    )


def _statement(name: str, there: SourceModule, ctx: StubContext) -> str | None:
    """Return an import statement binding *name* in the stub as the module *there* binds it."""
    here = ctx.source_module
    sym = there.symbols
    imp = next((i for i in reversed(sym.imports) if i.local == name and i.name != "*"), None)
    if imp is not None:
        if imp.module is None:
            return f"import {imp.name}" + (f" as {imp.asname}" if imp.asname else "")
        source = imp.module
        if source.startswith("."):
            dots = len(source) - len(source.lstrip("."))
            base = there.package.split(".")
            base = base[: len(base) - (dots - 1)] if dots > 1 else base
            source = ".".join(base + [source.lstrip(".")] if source.lstrip(".") else base)
            source = relative_module(source, here.name, here.is_package)
        alias = f" as {name}" if imp.name != name else ""
        return f"from {source} import {imp.name}{alias}"
    if name in _local_names(there) and not name.startswith("_"):
        return f"from {relative_module(there.name, here.name, here.is_package)} import {name}"
    return None


def bind_names(names: list[str], there: SourceModule, ctx: StubContext) -> bool:
    """Record the imports *names* need in the caller's stub; ``False`` when one cannot be bound."""
    here = ctx.source_module
    local = _local_names(here)
    needed: dict[str, str] = {}
    for name in names:
        if hasattr(builtins, name) or name in TYPING_CANDIDATES or name in TYPING_BACKPORTS:
            continue
        if name in local:
            stmt = ctx.import_map.get(name)
            if stmt is not None:
                needed[name] = stmt
            continue
        stmt = _statement(name, there, ctx)
        if stmt is None:
            return False
        needed[name] = stmt
    ctx.extra_imports.update(needed)
    return True


def bind_foreign(p: inspect.Parameter, h: dict, ctx: StubContext) -> ParamWithHints:
    """Make a parameter written in another module valid in this stub: import its names or drop them."""
    there = h.module if isinstance(h, SourceHints) else None
    if there is None or there is ctx.source_module:
        return p, h
    if isinstance(p.annotation, str):
        names = names_in(p.annotation)
        if names is None or not bind_names(names, there, ctx):
            p = p.replace(annotation=inspect.Parameter.empty)
    if isinstance(p.default, NonLiteralDefault) and repr(p.default) != "...":
        names = names_in(repr(p.default))
        if names is None or not bind_names(names, there, ctx):
            p = p.replace(default=_ELLIPSIS)
    return p, h
