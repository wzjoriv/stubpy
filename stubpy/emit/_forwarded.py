"""
``__init__(self, *args, **kwargs)`` forwarding unchanged to an overloaded compiled constructor: one ``@overload`` per variant.
"""
from __future__ import annotations

import ast
import inspect
from typing import Any

from stubpy.analysis.harvest.models import FunctionInfo
from stubpy.compiled.runtime import compiled_signatures
from stubpy.compiled.signatures import Param, Signature
from stubpy.compiled.typemap import caller_annotation
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Stage

from .signature import format_def

_VARIADICS = ["VAR_POSITIONAL", "VAR_KEYWORD"]


def _forwards_unchanged(info: FunctionInfo | None, method_name: str) -> bool:
    """True when *info* is ``(self, *args, **kwargs)`` passing both, and nothing else, to ``super().<method_name>``."""
    if info is None or info.hint_signature or [p.kind for p in info.raw_params[1:]] != _VARIADICS:
        return False
    target = [method_name]
    return (
        info.kwargs_forwarded_to == target and info.args_forwarded_to == target
        and not info.kwargs_positional_skips.get(method_name) and not info.kwargs_explicit_names.get(method_name)
        and not info.kwargs_consumed and not info.kwargs_injected and not info.kwargs_dynamic
        and not info.kwargs_unknown_starred and not info.kwargs_method_targets and not info.args_method_targets
    )


def _defining_base(cls: type, method_name: str) -> type | None:
    """The first class after *cls* in its MRO that defines *method_name*."""
    return next((base for base in cls.__mro__[1:] if method_name in vars(base)), None)


def _param_text(p: Param, owner_module: str, ctx: StubContext) -> str | None:
    """One parameter as stub text; ``None`` when its annotation cannot be written in the caller's stub."""
    annotation = None
    if p.annotation:
        annotation, imports = caller_annotation(p.annotation, owner_module, ctx.module_namespace)
        if annotation is None:
            return None
        ctx.extra_imports.update(imports)
    prefix = "**" if p.kind is inspect.Parameter.VAR_KEYWORD else "*" if p.kind is inspect.Parameter.VAR_POSITIONAL else ""
    text = prefix + p.name + (f": {annotation}" if annotation else "")
    if p.default is not None:
        default = p.default if _in_scope(p.default, ctx) else "..."
        text += f" = {default}" if annotation else f"={default}"
    return text


def _in_scope(default: str, ctx: StubContext) -> bool:
    """True for a literal default, or a dotted one whose root the caller's module binds."""
    try:
        ast.literal_eval(default)
        return True
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return default.split(".")[0] in ctx.module_namespace


def _variant(sig: Signature, owner_module: str, ctx: StubContext, indent: str, method_name: str) -> list[str] | None:
    """The ``@overload`` lines of one compiled signature, its receiver written as ``self``."""
    params = list(sig.params[1:])
    texts: list[str] = []
    prev = None
    star = False
    for p in params:
        if prev is inspect.Parameter.POSITIONAL_ONLY and p.kind is not inspect.Parameter.POSITIONAL_ONLY:
            texts.append("/")
        if p.kind is inspect.Parameter.KEYWORD_ONLY and not star:
            texts.append("*")
        star = star or p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_POSITIONAL)
        text = _param_text(p, owner_module, ctx)
        if text is None:
            return None
        texts.append(text)
        prev = p.kind
    if prev is inspect.Parameter.POSITIONAL_ONLY:
        texts.append("/")
    return [f"{indent}@overload"] + format_def(indent, "def", method_name, ["self", *texts], " -> None", len(texts))


def forwarded_overloads(cls: type, method_name: str, info: FunctionInfo | None, ctx: StubContext,
                        indent: str = "    ") -> list[str] | None:
    """The ``@overload`` variants of the compiled ``__init__`` that *cls*'s ``__init__`` forwards to unchanged.

    ``None`` unless *cls* defines ``__init__(self, *args, **kwargs)`` that
    only passes both to ``super().__init__`` and that constructor is
    compiled with several signatures whose annotations can all be written
    in the caller's stub.
    """
    if method_name != "__init__" or not _forwards_unchanged(info, method_name):
        return None
    base = _defining_base(cls, method_name)
    target: Any = vars(base).get(method_name) if base is not None else None
    sigs = compiled_signatures(target) if target is not None else []
    if len(sigs) < 2:
        return None
    lines: list[str] = []
    for sig in sigs:
        variant = _variant(sig, base.__module__, ctx, indent, method_name)
        if variant is None:
            return None
        lines.extend(variant)
    ctx.diagnostics.info(
        Stage.RESOLVE, f"{cls.__name__}.{method_name}",
        f"super().{method_name} is compiled with {len(sigs)} overloads; copied as @overload variants",
    )
    return lines
