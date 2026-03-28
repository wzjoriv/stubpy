"""
stubpy.generator
================

Top-level orchestrator for a complete stub-generation run.

This module exposes two public functions:

- :func:`collect_classes` — gathers classes from a loaded module in
  source-definition order (unchanged from v0.1).
- :func:`generate_stub` — the main entry point that sequences all
  pipeline stages and writes the ``.pyi`` file.

New additions
-------------
:func:`generate_stub` now performs an **AST pre-pass** (via
:func:`~stubpy.ast_pass.ast_harvest`) before the runtime-introspection
stages and builds a :class:`~stubpy.symbols.SymbolTable` that is stored
on the :class:`~stubpy.context.StubContext`.  The ``__all__`` list is
extracted and attached to the context.  All of this happens transparently;
the public signature and the generated ``.pyi`` output are identical to
v0.1 so all existing tests continue to pass.
"""
from __future__ import annotations

import inspect
import types as _builtin_types
from pathlib import Path

from .aliases import build_alias_registry
from .ast_pass import ast_harvest
from .context import StubContext
from .diagnostics import DiagnosticStage
from .emitter import generate_class_stub
from .imports import (
    collect_cross_imports,
    collect_typing_imports,
    scan_import_statements,
)
from .loader import load_module
from .symbols import build_symbol_table


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

    Examples
    --------
    >>> # Given shapes.py defining Shape, Circle, Rectangle in that order:
    >>> module, path, name = load_module("shapes.py")    # doctest: +SKIP
    >>> [c.__name__ for c in collect_classes(module, name)]  # doctest: +SKIP
    ['Shape', 'Circle', 'Rectangle']
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


def generate_stub(filepath: str, output_path: str | None = None) -> str:
    """Generate a ``.pyi`` stub file for the Python source at *filepath*.

    Runs the full pipeline in sequence:

    1. **Load** — import the source file as a live module.
    2. **AST pre-pass** — harvest structural metadata without side effects.
    3. **Scan imports** — parse AST to build a ``{name: stmt}`` map.
    4. **Build alias registry** — discover type-alias sub-modules.
    5. **Build symbol table** — merge AST + runtime data into a unified
       :class:`~stubpy.symbols.SymbolTable`.
    6. **Collect classes** — gather classes in source order.
    7. **Emit stubs** — generate class and method stubs.
    8. **Assemble header** — collect used ``typing`` names, type-module
       imports, and cross-file class imports.
    9. **Write** — write the complete ``.pyi`` to *output_path*.

    A fresh :class:`~stubpy.context.StubContext` is created for every
    call, making this function fully re-entrant.

    Parameters
    ----------
    filepath : str
        Path to the ``.py`` source file. Relative paths are resolved
        against the current working directory.
    output_path : str, optional
        Where to write the ``.pyi`` file. Defaults to the same directory
        and stem as *filepath* with a ``.pyi`` extension.

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
    stubpy.aliases.build_alias_registry : Stage 4 — alias discovery.
    stubpy.emitter.generate_class_stub : Stage 7 — stub emission.

    Examples
    --------
    >>> from stubpy import generate_stub
    >>> content = generate_stub("mypackage/shapes.py")  # doctest: +SKIP
    >>> content.splitlines()[0]  # doctest: +SKIP
    'from __future__ import annotations'
    """
    ctx = StubContext()

    # ── Stage 1: Load module ───────────────────────────────────────────
    module, path, module_name = load_module(filepath, diagnostics=ctx.diagnostics)
    source     = path.read_text(encoding="utf-8")

    # ── Stage 2: AST pre-pass ────────────────────────────────────────────
    try:
        ast_symbols = ast_harvest(source)
        ctx.diagnostics.info(
            DiagnosticStage.AST_PASS,
            path.name,
            f"Harvested {len(ast_symbols.classes)} classes, "
            f"{len(ast_symbols.functions)} functions, "
            f"{len(ast_symbols.variables)} variables",
        )
        # Extract __all__ into context
        if ast_symbols.all_exports is not None:
            ctx.all_exports = set(ast_symbols.all_exports)
    except Exception as exc:
        ctx.diagnostics.warning(
            DiagnosticStage.AST_PASS,
            path.name,
            f"AST pre-pass failed: {type(exc).__name__}: {exc}",
        )
        ast_symbols = None  # type: ignore[assignment]

    # ── Stage 3: Scan imports ─────────────────────────────────────────
    import_map = scan_import_statements(source)

    # ── Stage 4: Build alias registry ────────────────────────────────
    build_alias_registry(module, import_map, ctx)

    # ── Stage 5: Build symbol table ───────────────────────────────────────
    if ast_symbols is not None:
        try:
            all_exports_set = ctx.all_exports if ctx.config.respect_all else None
            ctx.symbol_table = build_symbol_table(
                module, module_name, ast_symbols, all_exports=all_exports_set
            )
            ctx.diagnostics.info(
                DiagnosticStage.SYMBOL_TABLE,
                path.name,
                f"Symbol table built: {len(ctx.symbol_table)} symbols",
            )
        except Exception as exc:
            ctx.diagnostics.warning(
                DiagnosticStage.SYMBOL_TABLE,
                path.name,
                f"Symbol table build failed: {type(exc).__name__}: {exc}",
            )

    # ── Stages 6-7: Collect classes and emit stubs ────────────────────
    classes = collect_classes(module, module_name)
    body    = "\n\n".join(generate_class_stub(cls, ctx) for cls in classes)

    # ── Stage 8: Assemble header ──────────────────────────────────────
    typing_names = collect_typing_imports(body)
    header_lines = ["from __future__ import annotations"]

    if typing_names:
        header_lines.append(f"from typing import {', '.join(typing_names)}")

    for alias, import_stmt in sorted(ctx.used_type_imports.items()):
        if import_stmt and f"{alias}." in body:
            header_lines.append(import_stmt)

    cross_imports = collect_cross_imports(module, module_name, body, import_map)
    for stmt in sorted(cross_imports):
        header_lines.append(stmt)

    header_lines.append("")
    content = "\n".join(header_lines) + "\n" + body + "\n"

    # ── Stage 9: Write ────────────────────────────────────────────────
    out = Path(output_path) if output_path else path.with_suffix(".pyi")
    out.write_text(content, encoding="utf-8")

    ctx.diagnostics.info(
        DiagnosticStage.GENERATOR,
        path.name,
        f"Stub written to {out}",
    )

    return content
