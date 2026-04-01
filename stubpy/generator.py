"""
stubpy.generator
================

Top-level orchestrator for a complete stub-generation run.

Two public functions are exposed:

- :func:`collect_classes` — gathers classes from a loaded module in
  source-definition order.
- :func:`generate_stub` — the main entry point that sequences all
  pipeline stages and writes the ``.pyi`` file.

Pipeline stages
---------------
1. **Load** — import the source file as a live module (skipped in
   ``AST_ONLY`` mode; graceful fallback in ``AUTO`` mode).
2. **AST pre-pass** — harvest structural metadata without executing code.
3. **Scan imports** — build a ``{name: stmt}`` map for the source file.
4. **Build alias registry** — discover type-alias sub-modules.
5. **Build symbol table** — merge AST + runtime data into a
   :class:`~stubpy.symbols.SymbolTable`.
6. **Emit stubs** — generate stubs for every public symbol in source
   order: aliases (TypeVar / TypeAlias), classes, overloaded functions,
   plain functions, and module-level variables.
   ``__all__`` filtering is applied via the symbol table.
7. **Assemble header** — collect ``typing`` names, type-module imports,
   special imports (``abc``, ``dataclasses``), and cross-file imports.
8. **Write** — write the complete ``.pyi`` to *output_path*.
"""
from __future__ import annotations

import inspect
import types as _builtin_types
from pathlib import Path

from .aliases import build_alias_registry
from .ast_pass import ast_harvest
from .context import ExecutionMode, StubContext
from .diagnostics import DiagnosticStage
from .emitter import (
    generate_alias_stub,
    generate_class_stub,
    generate_function_stub,
    generate_overload_group_stub,
    generate_variable_stub,
)
from .imports import (
    collect_cross_imports,
    collect_special_imports,
    collect_typing_imports,
    scan_import_statements,
)
from .loader import load_module
from .symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    VariableSymbol,
    build_symbol_table,
)


def collect_classes(
    module: _builtin_types.ModuleType,
    module_name: str,
) -> list[type]:
    """Return all classes *defined* in *module*, sorted by source-line order.

    Uses :func:`inspect.getmembers` filtered to classes whose
    ``__module__`` matches *module_name*, so only classes defined in the
    file itself are included — not classes imported into it.

    Parameters
    ----------
    module : types.ModuleType
        The loaded module returned by :func:`~stubpy.loader.load_module`.
    module_name : str
        Synthetic name assigned to the module by
        :func:`~stubpy.loader.load_module` (e.g.
        ``"_stubpy_target_graphics"``).

    Returns
    -------
    list of type
        Classes sorted by their first source line, mirroring source order.
    """
    classes: list[type] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ == module_name:
            classes.append(obj)

    def _source_line(c: type) -> int:
        try:
            return inspect.getsourcelines(c)[1]
        except Exception:
            return 0

    return sorted(classes, key=_source_line)


def generate_stub(
    filepath: str,
    output_path: str | None = None,
    ctx: StubContext | None = None,
) -> str:
    """Generate a ``.pyi`` stub file for the Python source at *filepath*.

    A fresh :class:`~stubpy.context.StubContext` is created when *ctx* is
    ``None``, making this function fully re-entrant.  Pass an explicit
    *ctx* to supply custom :class:`~stubpy.context.StubConfig` options
    (e.g. ``include_private=True``, ``execution_mode=ExecutionMode.AST_ONLY``)
    or to inspect diagnostics after the call.

    Execution modes
    ---------------
    ``RUNTIME`` (default)
        Execute the module; full introspection available.
    ``AST_ONLY``
        Parse the AST only — no module execution.  Safer for modules
        with import-time side effects; live types will be ``None``.
    ``AUTO``
        Execute when possible; fall back to AST-only on load failure.

    Parameters
    ----------
    filepath : str
        Path to the ``.py`` source file.
    output_path : str, optional
        Where to write the ``.pyi`` file. Defaults to the same directory
        and stem as *filepath* with a ``.pyi`` extension.
    ctx : StubContext, optional
        Pre-configured context. Created fresh when ``None``.

    Returns
    -------
    str
        Full stub content as a string, identical to what is written to disk.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    ImportError
        If the source file cannot be loaded as a module (``RUNTIME`` mode
        only; ``AUTO`` mode falls back to AST-only instead of raising).

    See Also
    --------
    stubpy.loader.load_module : Stage 1 — module loading.
    stubpy.ast_pass.ast_harvest : Stage 2 — AST pre-pass.
    stubpy.symbols.build_symbol_table : Stage 5 — symbol table.
    stubpy.emitter.generate_class_stub : Class stub emission.
    stubpy.emitter.generate_function_stub : Function stub emission.
    stubpy.emitter.generate_variable_stub : Variable stub emission.
    stubpy.emitter.generate_alias_stub : Alias/TypeVar stub emission.
    stubpy.emitter.generate_overload_group_stub : Overload group stub emission.
    """
    if ctx is None:
        ctx = StubContext()

    mode = ctx.config.execution_mode
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    source = path.read_text(encoding="utf-8")

    # ── Stage 1: Load module (respects execution_mode) ────────────────
    module: "_builtin_types.ModuleType | None" = None
    module_name: str = f"_stubpy_target_{path.stem}"

    if mode is ExecutionMode.AST_ONLY:
        ctx.diagnostics.info(
            DiagnosticStage.LOAD,
            path.name,
            "AST_ONLY mode — module execution skipped",
        )
    else:
        try:
            module, _resolved_path, module_name = load_module(
                filepath, diagnostics=ctx.diagnostics
            )
        except Exception as exc:
            if mode is ExecutionMode.AUTO:
                ctx.diagnostics.warning(
                    DiagnosticStage.LOAD,
                    path.name,
                    f"Module load failed, falling back to AST-only: "
                    f"{type(exc).__name__}: {exc}",
                )
                module = None
            else:
                raise  # RUNTIME mode — propagate the error

    # ── Stage 2: AST pre-pass ─────────────────────────────────────────
    try:
        ast_symbols = ast_harvest(source)
        ctx.diagnostics.info(
            DiagnosticStage.AST_PASS,
            path.name,
            f"Harvested {len(ast_symbols.classes)} classes, "
            f"{len(ast_symbols.functions)} functions, "
            f"{len(ast_symbols.variables)} variables, "
            f"{len(ast_symbols.typevar_decls)} type-var/alias decls",
        )
        if ast_symbols.all_exports is not None:
            ctx.all_exports = set(ast_symbols.all_exports)
        elif module is not None and hasattr(module, "__all__") and isinstance(
            module.__all__, (list, tuple)
        ):
            ctx.all_exports = set(module.__all__)
    except Exception as exc:
        ctx.diagnostics.warning(
            DiagnosticStage.AST_PASS,
            path.name,
            f"AST pre-pass failed: {type(exc).__name__}: {exc}",
        )
        ast_symbols = None  # type: ignore[assignment]

    # ── Stage 3: Scan imports ─────────────────────────────────────────
    import_map = scan_import_statements(source)

    # ── Stage 4: Build alias registry ─────────────────────────────────
    build_alias_registry(module, import_map, ctx)

    # ── Stage 5: Build symbol table ───────────────────────────────────
    if ast_symbols is not None:
        try:
            all_exports_set = (
                ctx.all_exports if ctx.config.respect_all else None
            )
            ctx.symbol_table = build_symbol_table(
                module,
                module_name,
                ast_symbols,
                all_exports=all_exports_set,
                include_private=ctx.config.include_private,
            )
            ctx.diagnostics.info(
                DiagnosticStage.SYMBOL_TABLE,
                path.name,
                f"Symbol table built: {len(ctx.symbol_table)} symbols "
                f"({sum(1 for s in ctx.symbol_table if isinstance(s, ClassSymbol))} classes, "
                f"{sum(1 for s in ctx.symbol_table if isinstance(s, FunctionSymbol))} functions, "
                f"{sum(1 for s in ctx.symbol_table if isinstance(s, VariableSymbol))} variables, "
                f"{sum(1 for s in ctx.symbol_table if isinstance(s, AliasSymbol))} aliases, "
                f"{sum(1 for s in ctx.symbol_table if isinstance(s, OverloadGroup))} overload-groups)",
            )
        except Exception as exc:
            ctx.diagnostics.warning(
                DiagnosticStage.SYMBOL_TABLE,
                path.name,
                f"Symbol table build failed: {type(exc).__name__}: {exc}",
            )

    # ── Stage 6: Emit stubs from symbol table ─────────────────────────
    if ctx.symbol_table is not None:
        # Collect overload-group names so we can suppress any matching
        # plain FunctionSymbol (the un-decorated implementation stub).
        overloaded_names: set[str] = {
            s.name for s in ctx.symbol_table if isinstance(s, OverloadGroup)
        }

        sections: list[str] = []
        for sym in ctx.symbol_table.sorted_by_line():
            stub: str = ""
            try:
                if isinstance(sym, AliasSymbol):
                    stub = generate_alias_stub(sym, ctx)
                elif isinstance(sym, ClassSymbol):
                    stub = _emit_class(sym, ctx)
                elif isinstance(sym, OverloadGroup):
                    stub = generate_overload_group_stub(sym, ctx)
                elif isinstance(sym, FunctionSymbol):
                    # Per PEP 484: suppress the implementation when
                    # @overload variants exist for this name.
                    if sym.name not in overloaded_names:
                        stub = generate_function_stub(sym, ctx)
                elif isinstance(sym, VariableSymbol):
                    stub = generate_variable_stub(sym, ctx)
            except Exception as exc:
                ctx.diagnostics.warning(
                    DiagnosticStage.EMIT,
                    sym.name,
                    f"Stub emission failed: {type(exc).__name__}: {exc}",
                )
            if stub:
                sections.append(stub)
        body = "\n\n".join(sections)
    else:
        # Fallback when symbol table could not be built
        if module is not None:
            classes = collect_classes(module, module_name)
            if ctx.all_exports is not None and ctx.config.respect_all:
                classes = [c for c in classes if c.__name__ in ctx.all_exports]
            body = "\n\n".join(generate_class_stub(cls, ctx) for cls in classes)
        else:
            body = ""

    # ── Stage 7: Assemble header ──────────────────────────────────────
    typing_names = collect_typing_imports(body)
    header_lines = ["from __future__ import annotations"]

    if typing_names:
        header_lines.append(f"from typing import {', '.join(typing_names)}")

    for module_name_s, names in sorted(collect_special_imports(body).items()):
        header_lines.append(f"from {module_name_s} import {', '.join(names)}")

    for alias, import_stmt in sorted(ctx.used_type_imports.items()):
        if import_stmt and f"{alias}." in body:
            header_lines.append(import_stmt)

    if module is not None:
        cross_imports = collect_cross_imports(module, module_name, body, import_map)
        for stmt in sorted(cross_imports):
            header_lines.append(stmt)

    header_lines.append("")
    content = "\n".join(header_lines) + "\n" + body + "\n"

    # ── Stage 8: Write ────────────────────────────────────────────────
    out = Path(output_path) if output_path else path.with_suffix(".pyi")
    out.write_text(content, encoding="utf-8")

    ctx.diagnostics.info(
        DiagnosticStage.GENERATOR,
        path.name,
        f"Stub written to {out}",
    )

    return content


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _emit_class(sym: ClassSymbol, ctx: StubContext) -> str:
    """Emit a class stub, preferring the live type but falling back to AST."""
    if sym.live_type is not None:
        return generate_class_stub(sym.live_type, ctx)
    # AST-only path: emit a minimal class block from the ClassInfo
    if sym.ast_info is not None:
        ci = sym.ast_info
        base_str = f"({', '.join(ci.bases)})" if ci.bases else ""
        dec_lines = [f"@{d}" for d in ci.decorators if d]
        return "\n".join(dec_lines + [f"class {ci.name}{base_str}:", "    ..."])
    return ""
