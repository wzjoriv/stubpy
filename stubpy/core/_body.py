"""Stub body emission: every symbol in source order, plus the hidden symbols the stub refers to."""
from __future__ import annotations

import inspect
import re
import types as _builtin_types

from stubpy.analysis.symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    VariableSymbol,
)
from stubpy.emit import (
    emit_class_from_ast,
    generate_alias_stub,
    generate_class_stub,
    generate_function_stub,
    generate_overload_group_stub,
    generate_variable_stub,
)

from ._layout import join_sections
from .context import StubContext
from .diagnostics import Stage

_WORD_RE = re.compile(r"\b[A-Za-z_]\w*\b")


def collect_classes(module: _builtin_types.ModuleType, module_name: str) -> list[type]:
    """Return the classes defined in *module* (not imported into it), in source order."""
    classes = [
        obj for obj in list(vars(module).values())
        if isinstance(obj, type) and obj.__module__ == module_name
    ]

    def _source_line(c: type) -> int:
        try:
            return inspect.getsourcelines(c)[1]
        except Exception:
            return 0

    return sorted(classes, key=_source_line)


def _emit_class(sym: ClassSymbol, ctx: StubContext) -> str:
    """Emit a class from its live type, or from AST metadata when there is none."""
    if sym.live_type is not None:
        return generate_class_stub(sym.live_type, ctx)
    if sym.ast_info is None:
        return ""
    return emit_class_from_ast(sym.ast_info, ctx)


def _emit_symbol(sym: object, overloaded_names: set[str], ctx: StubContext) -> tuple[str, bool]:
    """Return ``(stub, is_compact)`` for one symbol; compact stubs are single-line declarations."""
    if isinstance(sym, AliasSymbol):
        stub = generate_alias_stub(sym, ctx)
        return stub, bool(stub) and "\n" not in stub
    if isinstance(sym, ClassSymbol):
        return _emit_class(sym, ctx), False
    if isinstance(sym, OverloadGroup):
        return generate_overload_group_stub(sym, ctx), False
    if isinstance(sym, FunctionSymbol):
        if sym.name in overloaded_names:
            return "", False
        return generate_function_stub(sym, ctx), False
    if isinstance(sym, VariableSymbol):
        stub = generate_variable_stub(sym, ctx)
        return stub, bool(stub) and "\n" not in stub
    return "", False


def _emit_one(sym: object, overloaded_names: set[str], ctx: StubContext) -> tuple[str, bool]:
    """Emit one symbol, turning an emitter failure into a WARNING and an empty stub."""
    try:
        return _emit_symbol(sym, overloaded_names, ctx)
    except Exception as exc:
        ctx.diagnostics.warning(
            Stage.EMIT, getattr(sym, "name", "?"), f"Stub emission failed: {type(exc).__name__}: {exc}",
        )
        return "", False


def emit_body(module: _builtin_types.ModuleType | None, module_name: str, ctx: StubContext) -> str:
    """Emit every symbol in source order, or fall back to live classes without a table.

    Hidden symbols (private, or outside ``__all__``) that an emitted stub
    names, such as a TypeVar or a private base class, are emitted too, until
    nothing new is referenced.
    """
    table = ctx.symbol_table
    if table is None:
        if module is None:
            return ""
        classes = collect_classes(module, module_name)
        if ctx.all_exports is not None and ctx.config.respect_all:
            classes = [c for c in classes if c.__name__ in ctx.all_exports]
        return "\n\n".join(generate_class_stub(cls, ctx) for cls in classes)

    overloaded_names = {s.name for s in table if isinstance(s, OverloadGroup)}
    stubs: dict[int, tuple[object, str, bool]] = {}
    pending = list(table)
    while pending:
        for sym in pending:
            stub, compact = _emit_one(sym, overloaded_names, ctx)
            stubs[id(sym)] = (sym, stub, compact)
        hidden = table.hidden_names()
        referenced = {w for _, text, _ in stubs.values() for w in _WORD_RE.findall(text)} & hidden
        pending = [p for p in (table.promote(name) for name in sorted(referenced)) if p is not None]

    ordered = sorted(stubs.values(), key=lambda t: getattr(t[0], "lineno", 0))
    return join_sections([(stub, compact) for _, stub, compact in ordered if stub])
