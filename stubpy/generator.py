"""
stubpy.generator
================

Top-level orchestrator for stub generation — single files and entire packages.

Public functions
----------------
- :func:`generate_stub` — generate a ``.pyi`` file for one ``.py`` source file.
- :func:`generate_package` — recursively generate stubs for a whole package directory.
- :func:`collect_classes` — helper that returns classes from a module in source order.

``generate_stub`` pipeline
--------------------------
1. **Load** — import the source file as a live module (skipped in
   ``AST_ONLY`` mode; graceful fallback in ``AUTO`` mode).
2. **AST pre-pass** — harvest structural metadata without executing code.
3. **Scan imports** — build a ``{name: stmt}`` map for the source file.
4. **Build alias registry** — discover type-alias sub-modules.
5. **Build symbol table** — merge AST + runtime data into a
   :class:`~stubpy.symbols.SymbolTable`.
6. **Emit stubs** — generate stubs for every public symbol in source order:
   aliases (TypeVar / TypeAlias), classes, overloaded functions, plain
   functions, and module-level variables.  ``__all__`` filtering is applied
   via the symbol table.
7. **Assemble header** — collect ``typing`` names, type-module imports,
   special imports (``abc``, ``dataclasses``), and cross-file imports.
8. **Write** — write the complete ``.pyi`` to *output_path*.

``generate_package`` calls ``generate_stub`` for every ``.py`` file found
under the package root, mirroring the directory tree under the output
directory.
"""
from __future__ import annotations

import fnmatch
import inspect
import types as _builtin_types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .aliases import build_alias_registry
from .ast_pass import ast_harvest
from .context import StubConfig, ExecutionMode, StubContext
from .diagnostics import Diagnostic, DiagnosticStage
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
from .stub_merge import read_and_merge
from .symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    VariableSymbol,
    build_symbol_table,
)


# ---------------------------------------------------------------------------
# Package result
# ---------------------------------------------------------------------------

@dataclass
class PackageResult:
    """Outcome of a :func:`generate_package` run.

    Attributes
    ----------
    stubs_written : list of Path
        Absolute paths of every ``.pyi`` file successfully written.
    failed : list of tuple[Path, list[Diagnostic]]
        One entry per source file that raised an exception or accumulated
        ERROR-level diagnostics.  Each entry is ``(source_path, diagnostics)``.

    Examples
    --------
    >>> r = PackageResult()
    >>> r.summary()
    'Generated 0 stubs, 0 failed.'
    """
    stubs_written: list[Path]                          = field(default_factory=list)
    failed:        list[tuple[Path, list[Diagnostic]]] = field(default_factory=list)

    def summary(self) -> str:
        """Return a one-line human-readable summary.

        Examples
        --------
        >>> r = PackageResult(stubs_written=[Path("a.pyi")], failed=[])
        >>> r.summary()
        'Generated 1 stub, 0 failed.'
        """
        n = len(self.stubs_written)
        noun = "stub" if n == 1 else "stubs"
        return f"Generated {n} {noun}, {len(self.failed)} failed."


# ---------------------------------------------------------------------------
# Single-file stub generation
# ---------------------------------------------------------------------------

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
    generate_package : Batch generation for a whole package directory.
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

    # Populate module namespace for function-level kwargs resolution
    if module is not None:
        ctx.module_namespace = vars(module)

    # ── Stage 2: AST pre-pass ─────────────────────────────────────────
    try:
        ast_symbols = ast_harvest(source)

        # Honour # stubpy: ignore directive
        if ast_symbols.skip_file:
            ctx.diagnostics.info(
                DiagnosticStage.AST_PASS,
                path.name,
                "File skipped: '# stubpy: ignore' directive found",
            )
            out = Path(output_path) if output_path else path.with_suffix(".pyi")
            out.write_text("from __future__ import annotations\n", encoding="utf-8")
            return "from __future__ import annotations\n"

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

        # (stub_text, is_compact) pairs — tracked for smart spacing.
        # Single-line stubs (variables, TypeVar/TypeAlias declarations) are
        # "compact" and grouped together without blank lines between them.
        tagged: list[tuple[str, bool]] = []
        for sym in ctx.symbol_table.sorted_by_line():
            stub: str = ""
            is_compact = False
            try:
                if isinstance(sym, AliasSymbol):
                    stub = generate_alias_stub(sym, ctx)
                    # Single-line alias stubs group compactly with variables
                    is_compact = bool(stub) and "\n" not in stub
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
                    is_compact = bool(stub)
            except Exception as exc:
                ctx.diagnostics.warning(
                    DiagnosticStage.EMIT,
                    sym.name,
                    f"Stub emission failed: {type(exc).__name__}: {exc}",
                )
            if stub:
                tagged.append((stub, is_compact))

        body = _join_sections(tagged)
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
    # Use ordered insertion to deduplicate while preserving logical order.
    # Seen-set tracks which statements have already been added so that the
    # used_type_imports path and collect_cross_imports cannot produce duplicates.
    _seen_imports: set[str] = set()
    header_lines = ["from __future__ import annotations"]

    def _add_import(stmt: str) -> None:
        if stmt not in _seen_imports:
            _seen_imports.add(stmt)
            header_lines.append(stmt)

    if typing_names:
        typing_stmt = f"from typing import {', '.join(typing_names)}"
        _add_import(typing_stmt)

    for module_name_s, names in sorted(collect_special_imports(body).items()):
        _add_import(f"from {module_name_s} import {', '.join(names)}")

    for alias, import_stmt in sorted(ctx.used_type_imports.items()):
        if import_stmt and f"{alias}." in body:
            _add_import(import_stmt)

    if module is not None:
        cross_imports = collect_cross_imports(module, module_name, body, import_map)
        for stmt in sorted(cross_imports):
            _add_import(stmt)

    header_lines.append("")
    content = "\n".join(header_lines) + "\n" + body + "\n"

    # ── Stage 8: Write ────────────────────────────────────────────────
    out = Path(output_path) if output_path else path.with_suffix(".pyi")
    if ctx.config.incremental_update:
        final_content = read_and_merge(out, content)
        if final_content != content:
            ctx.diagnostics.info(
                DiagnosticStage.GENERATOR,
                path.name,
                "Incremental update: merged with existing stub",
            )
    else:
        final_content = content
    out.write_text(final_content, encoding="utf-8")
    content = final_content

    ctx.diagnostics.info(
        DiagnosticStage.GENERATOR,
        path.name,
        f"Stub written to {out}",
    )

    return content


# ---------------------------------------------------------------------------
# Package (batch) stub generation
# ---------------------------------------------------------------------------

def generate_package(
    package_dir: str | Path,
    output_dir:  str | Path | None = None,
    ctx_factory: "Callable[[Path, Path], StubContext] | Callable[[], StubContext] | None" = None,
    config:      StubConfig | None = None,
) -> PackageResult:
    """Generate ``.pyi`` stubs for every ``.py`` file in *package_dir*.

    Walks *package_dir* recursively and calls :func:`generate_stub` for
    each ``.py`` source file.  For every sub-directory that contains an
    ``__init__.py``, the corresponding ``__init__.pyi`` is created under
    *output_dir* (if it was not already produced by ``generate_stub``).

    Files matching any pattern in ``config.exclude`` are skipped.  Files
    that fail with an exception or ERROR-level diagnostics are recorded in
    :attr:`PackageResult.failed` and processing continues.

    Parameters
    ----------
    package_dir : str or Path
        Root of the package to process.
    output_dir : str or Path or None
        Directory where stubs are written.  The subdirectory structure of
        *package_dir* is reproduced under *output_dir*.  When ``None``
        (default), stubs are written alongside the source files.
    ctx_factory : callable or None
        Called to produce a fresh :class:`~stubpy.context.StubContext` for
        each file.  Two signatures are accepted:

        - ``ctx_factory()`` — called with no arguments (backward compatible).
        - ``ctx_factory(source_path, output_path)`` — called with the
          absolute :class:`~pathlib.Path` of the source ``.py`` file and
          the destination ``.pyi`` path, allowing per-file customisation
          (e.g. different ``execution_mode`` for slow modules, extra exclude
          patterns for generated files, custom annotation handlers).

        When ``None``, a context derived from *config* (or a default config)
        is used.
    config : StubConfig or None
        Configuration applied when *ctx_factory* is ``None``.  When both
        are ``None``, :class:`~stubpy.context.StubConfig` defaults are used.

    Returns
    -------
    PackageResult
        Contains ``stubs_written`` (success paths) and ``failed``
        (``(path, diagnostics)`` pairs for errored files).

    Raises
    ------
    FileNotFoundError
        If *package_dir* does not exist on disk.

    Examples
    --------
    >>> from stubpy import generate_package
    >>> result = generate_package("mypackage/", "stubs/")  # doctest: +SKIP
    >>> print(result.summary())                            # doctest: +SKIP
    Generated 8 stubs, 0 failed.
    """
    pkg_root = Path(package_dir).resolve()
    if not pkg_root.exists():
        raise FileNotFoundError(f"Package directory not found: {pkg_root}")

    out_root: Path | None = Path(output_dir).resolve() if output_dir else None
    effective_config = config or StubConfig()
    exclude_patterns: list[str] = list(effective_config.exclude or [])

    result = PackageResult()

    for py_file in sorted(pkg_root.rglob("*.py")):
        rel = py_file.relative_to(pkg_root)

        # Apply exclude patterns against the relative POSIX path
        if any(fnmatch.fnmatch(rel.as_posix(), pat) for pat in exclude_patterns):
            continue

        # Compute output path
        if out_root is not None:
            out_pyi = out_root / rel.with_suffix(".pyi")
            out_pyi.parent.mkdir(parents=True, exist_ok=True)
            out_path: str | None = str(out_pyi)
        else:
            out_path = None  # generate_stub writes alongside source

        # Build a fresh context for this file.
        # ctx_factory accepts either () or (source_path, output_path).
        if ctx_factory is not None:
            try:
                import inspect as _inspect
                _sig = _inspect.signature(ctx_factory)
                _nparams = sum(
                    1 for p in _sig.parameters.values()
                    if p.default is _inspect.Parameter.empty
                    and p.kind not in (
                        _inspect.Parameter.VAR_POSITIONAL,
                        _inspect.Parameter.VAR_KEYWORD,
                    )
                )
                if _nparams >= 2:
                    _out_for_factory = Path(out_path) if out_path else py_file.with_suffix(".pyi")
                    ctx = ctx_factory(py_file, _out_for_factory)
                else:
                    ctx = ctx_factory()
            except (TypeError, ValueError):
                ctx = ctx_factory()
        else:
            ctx = StubContext(config=effective_config)

        try:
            generate_stub(str(py_file), out_path, ctx=ctx)
            written = Path(out_path) if out_path else py_file.with_suffix(".pyi")
            if not ctx.diagnostics.has_errors():
                result.stubs_written.append(written)
            else:
                result.failed.append((py_file, ctx.diagnostics.errors))
        except Exception:
            result.failed.append((py_file, ctx.diagnostics.errors))

    # Ensure every sub-package directory has an __init__.pyi
    if out_root is not None:
        _ensure_init_pyi(pkg_root, out_root)

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _join_sections(tagged: list[tuple[str, bool]]) -> str:
    """Join stub sections with smart spacing based on symbol kind.

    Consecutive *variable* or *alias* stubs are joined with a single newline
    so they form a compact block — no blank line between ``X: int`` and
    ``Y: str``, or between ``Color: TypeAlias = ...`` and
    ``Length: TypeAlias = ...``.  All other transitions use a double newline.

    Parameters
    ----------
    tagged : list of (stub_text, is_compact) pairs
        ``is_compact`` is ``True`` for variable and single-line alias stubs.

    Returns
    -------
    str
        The assembled stub body.

    Examples
    --------
    >>> _join_sections([("X: int", True), ("Y: str", True), ("def f(): ...", False)])
    'X: int\\nY: str\\n\\ndef f(): ...'
    """
    if not tagged:
        return ""
    parts = [tagged[0][0]]
    for (_, prev_compact), (text, curr_compact) in zip(tagged, tagged[1:]):
        sep = "\n" if (prev_compact and curr_compact) else "\n\n"
        parts.append(sep + text)
    return "".join(parts)


def _emit_class(sym: ClassSymbol, ctx: StubContext) -> str:
    """Emit a class stub, preferring the live type but falling back to AST info."""
    if sym.live_type is not None:
        return generate_class_stub(sym.live_type, ctx)
    # AST-only path: emit a minimal class block from ClassInfo
    if sym.ast_info is not None:
        ci = sym.ast_info
        base_str = f"({', '.join(ci.bases)})" if ci.bases else ""
        dec_lines = [f"@{d}" for d in ci.decorators if d]
        return "\n".join(dec_lines + [f"class {ci.name}{base_str}:", "    ..."])
    return ""


def _ensure_init_pyi(pkg_root: Path, out_root: Path) -> None:
    """Create empty ``__init__.pyi`` for sub-packages that need one.

    A sub-package is any directory under *pkg_root* that contains an
    ``__init__.py``.  If the corresponding ``__init__.pyi`` was not already
    produced by :func:`generate_stub` (e.g. because ``__init__.py`` is
    empty or errored), we write a minimal placeholder so type checkers
    recognise the directory as a package.
    """
    for init_py in pkg_root.rglob("__init__.py"):
        rel_dir = init_py.parent.relative_to(pkg_root)
        out_init = out_root / rel_dir / "__init__.pyi"
        if not out_init.exists():
            out_init.parent.mkdir(parents=True, exist_ok=True)
            out_init.write_text(
                "# Stub package marker — generated by stubpy.\n",
                encoding="utf-8",
            )
