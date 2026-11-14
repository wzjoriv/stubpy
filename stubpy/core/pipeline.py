"""Single-file stub generation: load, harvest, build the symbol table, emit, write."""
from __future__ import annotations

import ast
import inspect
import tokenize
import types as _builtin_types
from pathlib import Path

from stubpy._constants import FUTURE_IMPORT, TARGET_MODULE_PREFIX
from stubpy.analysis.aliases import build_alias_registry
from stubpy.analysis.harvest import ASTSymbols, ast_harvest
from stubpy.analysis.imports import scan_import_statements
from stubpy.analysis.loader import ModuleLoader, ModuleReplacedError, describe_load_error
from stubpy.analysis.symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    VariableSymbol,
    build_symbol_table,
)
from stubpy.config.options import ExecutionMode
from stubpy.emit import (
    emit_class_from_ast,
    generate_alias_stub,
    generate_class_stub,
    generate_function_stub,
    generate_overload_group_stub,
    generate_variable_stub,
    reexport_lines,
)
from stubpy.merge import read_and_merge
from stubpy.resolve import introspection_cache

from ._layout import join_sections
from .context import StubContext
from .diagnostics import DiagnosticStage
from .header import build_header


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


def generate_stub(
    filepath: str,
    output_path: str | None = None,
    ctx: StubContext | None = None,
) -> str:
    """Generate a ``.pyi`` stub for the Python source at *filepath*.

    The module is executed according to ``ctx.config.execution_mode``:
    ``RUNTIME`` imports it, ``AST_ONLY`` only parses it, and ``AUTO`` falls
    back to parsing when the import fails.  A file inside a package is
    imported by its dotted name, so relative imports work.  A file whose
    first lines carry ``# stubpy: ignore`` gets an empty stub.

    Parameters
    ----------
    filepath : str
        Path to the ``.py`` source file.
    output_path : str, optional
        Where to write the stub.  Defaults to *filepath* with a ``.pyi`` suffix.
    ctx : StubContext, optional
        Pre-configured context; a fresh one is created when ``None``.

    Returns
    -------
    str
        The stub content, as written to disk.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    ImportError
        If the module cannot be loaded in ``RUNTIME`` mode.

    Examples
    --------
    >>> from stubpy import generate_stub, StubContext, StubConfig
    >>> content = generate_stub("pkg/module.py")  # doctest: +SKIP
    >>> ctx = StubContext(config=StubConfig(include_private=True))
    >>> content = generate_stub("pkg/module.py", "out/module.pyi", ctx=ctx)  # doctest: +SKIP
    """
    if ctx is None:
        ctx = StubContext()

    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    out = Path(output_path) if output_path else path.with_suffix(".pyi")

    owns_loader = ctx.module_loader is None
    if owns_loader:
        ctx.module_loader = ModuleLoader()
    try:
        with introspection_cache():
            content = _render(path, ctx)
    finally:
        if owns_loader:
            ctx.module_loader.close()
            ctx.module_loader = None
    return _write(content, out, path, ctx)


def _read_source(path: Path) -> str:
    """Read *path* honouring its encoding cookie and BOM."""
    with tokenize.open(path) as fh:
        return fh.read()


def _parse(source: str, path: Path, ctx: StubContext) -> ast.Module | None:
    """Parse *source* once for every AST consumer; record an ERROR when it does not parse."""
    try:
        return ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError) as exc:
        ctx.diagnostics.error(
            DiagnosticStage.AST_PASS, path.name,
            f"Source does not parse on this Python version: {type(exc).__name__}: {exc}",
        )
        return None


def _render(path: Path, ctx: StubContext) -> str:
    """Return the stub text for *path*."""
    source = _read_source(path)
    tree = _parse(source, path, ctx)

    ast_symbols = _harvest(source, tree, path, ctx)
    if ast_symbols is not None and ast_symbols.skip_file:
        return FUTURE_IMPORT + "\n"

    module, module_name = _load(path, ctx)
    if module is not None:
        ctx.module_namespace = vars(module)
    ctx.module_name = module_name
    _record_all(ast_symbols, module, ctx)

    import_map = scan_import_statements(tree) if tree is not None else {}
    ctx.import_map = import_map
    build_alias_registry(module, import_map, ctx)

    if ast_symbols is not None:
        _build_table(module, module_name, ast_symbols, path, ctx)

    body = _emit_body(module, module_name, ctx)
    exports = reexport_lines(ast_symbols, ctx, is_package=path.name == "__init__.py") if ast_symbols else []
    header_lines = build_header(body, ctx, module, module_name, import_map, exports)
    return "\n".join(header_lines + [""]) + "\n" + body + "\n"


def _load(path: Path, ctx: StubContext) -> tuple[_builtin_types.ModuleType | None, str]:
    """Load the module unless the execution mode forbids it; return ``(module, module_name)``."""
    mode = ctx.config.execution_mode
    module_name = f"{TARGET_MODULE_PREFIX}{path.stem}"

    if mode is ExecutionMode.AST_ONLY:
        ctx.diagnostics.info(DiagnosticStage.LOAD, path.name, "AST_ONLY mode — module execution skipped")
        return None, module_name

    try:
        loaded = ctx.module_loader.load(path, ctx.diagnostics)
    except FileNotFoundError:
        raise
    except ModuleReplacedError as exc:
        ctx.diagnostics.warning(DiagnosticStage.LOAD, path.name, f"{exc}; stubbing from the AST instead")
        return None, module_name
    except Exception as exc:
        reason = describe_load_error(exc)
        if mode is ExecutionMode.AUTO:
            ctx.diagnostics.warning(
                DiagnosticStage.LOAD, path.name,
                f"Module load failed, falling back to AST-only: {reason}",
            )
            return None, module_name
        ctx.diagnostics.error(DiagnosticStage.LOAD, path.name, f"Module execution failed: {reason}")
        raise
    return loaded.module, loaded.name


def _record_all(
    ast_symbols: ASTSymbols | None, module: _builtin_types.ModuleType | None, ctx: StubContext,
) -> None:
    """Set ``ctx.all_exports`` from the literal ``__all__``, else from the live module's string entries."""
    if ast_symbols is not None and ast_symbols.all_exports is not None:
        ctx.all_exports = set(ast_symbols.all_exports)
        return
    try:
        runtime_all = getattr(module, "__all__", None) if module is not None else None
    except Exception:
        runtime_all = None
    if isinstance(runtime_all, (list, tuple)):
        ctx.all_exports = {n for n in runtime_all if isinstance(n, str)}


def _harvest(source: str, tree: ast.Module | None, path: Path, ctx: StubContext) -> ASTSymbols | None:
    """Run the AST pre-pass on the parsed *tree*; ``None`` if the pass fails."""
    try:
        ast_symbols = ast_harvest(source, tree=tree)
        if ast_symbols.skip_file:
            ctx.diagnostics.info(
                DiagnosticStage.AST_PASS,
                path.name,
                "File skipped: '# stubpy: ignore' directive found",
            )
            return ast_symbols

        ctx.diagnostics.info(
            DiagnosticStage.AST_PASS,
            path.name,
            f"Harvested {len(ast_symbols.classes)} classes, "
            f"{len(ast_symbols.functions)} functions, "
            f"{len(ast_symbols.variables)} variables, "
            f"{len(ast_symbols.typevar_decls)} type-var/alias decls",
        )
    except Exception as exc:
        ctx.diagnostics.warning(
            DiagnosticStage.AST_PASS,
            path.name,
            f"AST pre-pass failed: {type(exc).__name__}: {exc}",
        )
        return None
    return ast_symbols


def _build_table(
    module: _builtin_types.ModuleType | None,
    module_name: str,
    ast_symbols: ASTSymbols,
    path: Path,
    ctx: StubContext,
) -> None:
    """Build ``ctx.symbol_table``, recording a warning instead of raising on failure."""
    try:
        ctx.symbol_table = build_symbol_table(
            module,
            module_name,
            ast_symbols,
            all_exports=ctx.all_exports if ctx.config.respect_all else None,
            include_private=ctx.config.include_private,
            diagnostics=ctx.diagnostics,
        )
        table = ctx.symbol_table
        ctx.diagnostics.info(
            DiagnosticStage.SYMBOL_TABLE,
            path.name,
            f"Symbol table built: {len(table)} symbols "
            f"({sum(1 for s in table if isinstance(s, ClassSymbol))} classes, "
            f"{sum(1 for s in table if isinstance(s, FunctionSymbol))} functions, "
            f"{sum(1 for s in table if isinstance(s, VariableSymbol))} variables, "
            f"{sum(1 for s in table if isinstance(s, AliasSymbol))} aliases, "
            f"{sum(1 for s in table if isinstance(s, OverloadGroup))} overload-groups)",
        )
    except Exception as exc:
        ctx.diagnostics.warning(
            DiagnosticStage.SYMBOL_TABLE,
            path.name,
            f"Symbol table build failed: {type(exc).__name__}: {exc}",
        )


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
        return stub, bool(stub)
    return "", False


def _emit_body(
    module: _builtin_types.ModuleType | None, module_name: str, ctx: StubContext,
) -> str:
    """Emit every symbol in source order, or fall back to live classes without a table."""
    if ctx.symbol_table is None:
        if module is None:
            return ""
        classes = collect_classes(module, module_name)
        if ctx.all_exports is not None and ctx.config.respect_all:
            classes = [c for c in classes if c.__name__ in ctx.all_exports]
        return "\n\n".join(generate_class_stub(cls, ctx) for cls in classes)

    overloaded_names = {s.name for s in ctx.symbol_table if isinstance(s, OverloadGroup)}
    tagged: list[tuple[str, bool]] = []
    for sym in ctx.symbol_table.sorted_by_line():
        try:
            stub, is_compact = _emit_symbol(sym, overloaded_names, ctx)
        except Exception as exc:
            ctx.diagnostics.warning(
                DiagnosticStage.EMIT,
                sym.name,
                f"Stub emission failed: {type(exc).__name__}: {exc}",
            )
            continue
        if stub:
            tagged.append((stub, is_compact))
    return join_sections(tagged)


def _write(content: str, out: Path, path: Path, ctx: StubContext) -> str:
    """Write the stub, merging into the existing file in incremental mode; return the final text."""
    if ctx.config.incremental_update:
        final_content, merge_warning = read_and_merge(out, content)
        if merge_warning is not None:
            ctx.diagnostics.warning(DiagnosticStage.GENERATOR, path.name, str(merge_warning))
        elif final_content != content:
            ctx.diagnostics.info(
                DiagnosticStage.GENERATOR,
                path.name,
                "Incremental update: merged with existing stub",
            )
    else:
        final_content = content
    out.write_text(final_content, encoding="utf-8")

    ctx.diagnostics.info(DiagnosticStage.GENERATOR, path.name, f"Stub written to {out}")
    return final_content
