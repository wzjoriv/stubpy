"""Single-module stub rendering: load, harvest, build the symbol table, emit."""
from __future__ import annotations

import ast
import types as _builtin_types
from pathlib import Path

from stubpy._constants import TARGET_MODULE_PREFIX
from stubpy.analysis import vfs
from stubpy.analysis.aliases import build_alias_registry
from stubpy.analysis.exports import runtime_all, star_names, static_all
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
from stubpy.compiled.detect import is_extension_file
from stubpy.config.options import Mode, VersionBranches
from stubpy.emit import reexport_lines
from stubpy.resolve import introspection_cache
from stubpy.resolve.static import SourceIndex

from ._body import emit_body
from ._compiled import render_compiled
from ._layout import all_block, stub_text
from ._lazy import lazy_reexports
from .context import StubContext
from .diagnostics import Stage
from .header import build_header


def render_module(path: str | Path, ctx: StubContext) -> str:
    """Return the stub text for the ``.py`` file or extension module at *path*; nothing is written.

    The module is imported according to ``ctx.config.mode``, by its dotted
    name when it sits in a package.  An extension module (``.pyd`` / ``.so``)
    is always imported and introspected.  Load failures raise; everything
    else is recorded in ``ctx.diagnostics``.
    """
    path = Path(path).resolve()
    if not vfs.is_file(path):
        raise FileNotFoundError(f"No such file: {path}")
    owns_loader = ctx.module_loader is None
    if owns_loader:
        ctx.module_loader = ModuleLoader()
    try:
        with introspection_cache():
            if is_extension_file(path):
                return render_compiled(path, ctx)
            return _render(path, ctx)
    finally:
        if owns_loader:
            ctx.module_loader.close()
            ctx.module_loader = None


def _read_source(path: Path) -> str:
    """Read *path* honouring its encoding cookie and BOM."""
    return vfs.read_source(path)


def _parse(source: str, path: Path, ctx: StubContext) -> ast.Module | None:
    """Parse *source* once for every AST consumer; record an ERROR when it does not parse."""
    try:
        return ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError) as exc:
        ctx.diagnostics.error(
            Stage.AST_PASS, path.name,
            f"Source does not parse on this Python version: {type(exc).__name__}: {exc}",
        )
        return None


def _render(path: Path, ctx: StubContext) -> str:
    """Return the stub text for *path*."""
    source = _read_source(path)
    tree = _parse(source, path, ctx)

    ast_symbols = _harvest(source, tree, path, ctx)
    if ast_symbols is not None and ast_symbols.skip_file:
        return ""

    module, module_name = _load(path, ctx)
    if module is not None:
        ctx.module_namespace = vars(module)
    if ast_symbols is not None:
        if ctx.source_index is None:
            ctx.source_index = SourceIndex()
        ctx.source_module = ctx.source_index.module_at(path)
    ctx.module_name = module_name
    _record_all(ast_symbols, module, path, ctx)
    _record_stars(ast_symbols, module, path, ctx)

    import_map = scan_import_statements(tree) if tree is not None else {}
    branch_bound: set[str] = set()
    if ast_symbols is not None:
        ctx.branch_imports = [imp for imp in ast_symbols.imports if imp.branch]
        branch_bound = {i.local for i in ctx.branch_imports} - {i.local for i in ast_symbols.imports if not i.branch}
        import_map = {k: v for k, v in import_map.items() if k not in branch_bound}
    ctx.import_map = import_map
    build_alias_registry(module, import_map, ctx)

    lazy: list[str] = []
    if ast_symbols is not None:
        _build_table(module, module_name, ast_symbols, path, ctx)
        lazy = lazy_reexports(tree, module, ast_symbols, ctx)

    body = emit_body(module, module_name, ctx)
    exports = reexport_lines(ast_symbols, ctx, is_package=path.name == "__init__.py") if ast_symbols else []
    exports += [line for line in lazy if line not in exports]
    header = "\n".join(build_header(body, ctx, module, module_name, import_map, exports, branch_bound))
    return stub_text(header, all_block(ctx.all_order, header, body), body)


def _load(path: Path, ctx: StubContext) -> tuple[_builtin_types.ModuleType | None, str]:
    """Load the module unless the execution mode forbids it; return ``(module, module_name)``."""
    mode = ctx.config.mode
    module_name = f"{TARGET_MODULE_PREFIX}{path.stem}"

    if mode is Mode.AST:
        ctx.diagnostics.info(Stage.LOAD, path.name, "AST mode — module execution skipped")
        return None, module_name

    try:
        loaded = ctx.module_loader.load(path, ctx.diagnostics)
    except FileNotFoundError:
        raise
    except ModuleReplacedError as exc:
        ctx.diagnostics.warning(Stage.LOAD, path.name, f"{exc}; stubbing from the AST instead")
        return None, module_name
    except Exception as exc:
        reason = describe_load_error(exc)
        if mode is Mode.AUTO:
            ctx.diagnostics.warning(
                Stage.LOAD, path.name,
                f"Module load failed, falling back to AST-only: {reason}",
            )
            return None, module_name
        ctx.diagnostics.error(Stage.LOAD, path.name, f"Module execution failed: {reason}")
        raise
    return loaded.module, loaded.name


def _record_all(
    ast_symbols: ASTSymbols | None,
    module: _builtin_types.ModuleType | None,
    path: Path,
    ctx: StubContext,
) -> None:
    """Set ``ctx.all_exports`` from a literal ``__all__``, else the live module's, else the source with its splices."""
    names: list[str] | None = None
    if ast_symbols is not None and ast_symbols.all_exports is not None and not ast_symbols.all_spliced:
        names = list(ast_symbols.all_exports)
    if names is None:
        names = runtime_all(module)
    if names is None and ast_symbols is not None and ast_symbols.all_exports is not None:
        names = static_all(path, ast_symbols)
    if names is not None:
        ctx.all_exports = set(names)
        ctx.all_order = list(dict.fromkeys(names))


def _record_stars(
    ast_symbols: ASTSymbols | None, module: _builtin_types.ModuleType | None, path: Path, ctx: StubContext,
) -> None:
    """Record the names each ``from m import *`` binds, when ``m`` declares ``__all__``."""
    if ast_symbols is None:
        return
    package = getattr(module, "__package__", None) if module is not None else None
    for imp in ast_symbols.imports:
        if imp.name == "*" and imp.module:
            names = star_names(imp.module, path, package, live=module is not None)
            if names is not None:
                ctx.star_exports[imp.module] = names


def _harvest(source: str, tree: ast.Module | None, path: Path, ctx: StubContext) -> ASTSymbols | None:
    """Run the AST pre-pass on the parsed *tree*; ``None`` if the pass fails."""
    try:
        ast_symbols = ast_harvest(
            source, tree=tree, version_branches=ctx.config.version_branches is VersionBranches.EMIT,
        )
        if ast_symbols.skip_file:
            ctx.diagnostics.info(
                Stage.AST_PASS,
                path.name,
                "File skipped: '# stubpy: ignore' directive found",
            )
            return ast_symbols

        ctx.diagnostics.info(
            Stage.AST_PASS,
            path.name,
            f"Harvested {len(ast_symbols.classes)} classes, "
            f"{len(ast_symbols.functions)} functions, "
            f"{len(ast_symbols.variables)} variables, "
            f"{len(ast_symbols.typevar_decls)} type-var/alias decls",
        )
    except Exception as exc:
        ctx.diagnostics.warning(
            Stage.AST_PASS,
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
            Stage.SYMBOL_TABLE,
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
            Stage.SYMBOL_TABLE,
            path.name,
            f"Symbol table build failed: {type(exc).__name__}: {exc}",
        )
