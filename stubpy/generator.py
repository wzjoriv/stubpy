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
1. **Load** — import the source file as a live module.
2. **AST pre-pass** — harvest structural metadata without executing code.
3. **Scan imports** — build a ``{name: stmt}`` map for the source file.
4. **Build alias registry** — discover type-alias sub-modules.
5. **Build symbol table** — merge AST + runtime data into a
   :class:`~stubpy.symbols.SymbolTable`.
6. **Emit stubs** — generate stubs for every public symbol in source
   order: classes, module-level functions, and module-level variables.
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
from .context import StubContext
from .diagnostics import DiagnosticStage
from .emitter import (
    generate_class_stub,
    generate_function_stub,
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
    ClassSymbol,
    FunctionSymbol,
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
    (e.g. ``include_private=True``) or to inspect diagnostics after the
    call.

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
        If the source file cannot be loaded as a module.

    See Also
    --------
    stubpy.loader.load_module : Stage 1 — module loading.
    stubpy.ast_pass.ast_harvest : Stage 2 — AST pre-pass.
    stubpy.symbols.build_symbol_table : Stage 5 — symbol table.
    stubpy.emitter.generate_class_stub : Class stub emission.
    stubpy.emitter.generate_function_stub : Function stub emission.
    stubpy.emitter.generate_variable_stub : Variable stub emission.
    """
    if ctx is None:
        ctx = StubContext()

    # ── Stage 1: Load module ───────────────────────────────────────────
    module, path, module_name = load_module(filepath, diagnostics=ctx.diagnostics)
    source = path.read_text(encoding="utf-8")

    # ── Stage 2: AST pre-pass ─────────────────────────────────────────
    try:
        ast_symbols = ast_harvest(source)
        ctx.diagnostics.info(
            DiagnosticStage.AST_PASS,
            path.name,
            f"Harvested {len(ast_symbols.classes)} classes, "
            f"{len(ast_symbols.functions)} functions, "
            f"{len(ast_symbols.variables)} variables",
        )
        if ast_symbols.all_exports is not None:
            ctx.all_exports = set(ast_symbols.all_exports)
        elif hasattr(module, "__all__") and isinstance(module.__all__, (list, tuple)):
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
                f"{sum(1 for s in ctx.symbol_table if isinstance(s, VariableSymbol))} variables)",
            )
        except Exception as exc:
            ctx.diagnostics.warning(
                DiagnosticStage.SYMBOL_TABLE,
                path.name,
                f"Symbol table build failed: {type(exc).__name__}: {exc}",
            )

    # ── Stage 6: Emit stubs from symbol table ─────────────────────────
    if ctx.symbol_table is not None:
        sections: list[str] = []
        for sym in ctx.symbol_table.sorted_by_line():
            stub: str = ""
            try:
                if isinstance(sym, ClassSymbol):
                    if sym.live_type is not None:
                        stub = generate_class_stub(sym.live_type, ctx)
                elif isinstance(sym, FunctionSymbol):
                    stub = generate_function_stub(sym, ctx)
                elif isinstance(sym, VariableSymbol):
                    stub = generate_variable_stub(sym, ctx)
                # AliasSymbol and OverloadGroup are handled in future work
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
        classes = collect_classes(module, module_name)
        if ctx.all_exports is not None and ctx.config.respect_all:
            classes = [c for c in classes if c.__name__ in ctx.all_exports]
        body = "\n\n".join(generate_class_stub(cls, ctx) for cls in classes)

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
