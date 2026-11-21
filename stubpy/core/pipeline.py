"""
Single-module stub rendering: load, harvest, build the symbol table, emit.
"""
from __future__ import annotations

import ast
import re
import types as _builtin_types
import warnings
from pathlib import Path

from stubpy._constants import TARGET_MODULE_PREFIX
from stubpy.analysis import vfs
from stubpy.analysis.aliases import build_alias_registry
from stubpy.analysis.exports import runtime_all, star_names, static_all
from stubpy.analysis.harvest import ASTSymbols, ast_harvest
from stubpy.analysis.loader import ImportBlockedError, ModuleLoader, ModuleReplacedError, describe_load_error
from stubpy.analysis.symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    VariableSymbol,
    build_symbol_table,
)
from stubpy.analysis.syntax import NewerSyntaxError, required_python
from stubpy.compiled.detect import is_extension_file
from stubpy.config.options import VersionBranches
from stubpy.core._constants import IMPORT_FAILED_PREFIX
from stubpy.emit import reexport_lines
from stubpy.resolve import introspection_cache
from stubpy.resolve.static import SourceIndex
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Stage

from ._body import emit_body
from ._compiled import render_compiled, render_cython_source
from ._layout import all_block, stub_text
from ._lazy import lazy_reexports
from ._parsed import ParsedFile, parsed_facts, source_digest
from .header import build_header


def render_module(path: str | Path, ctx: StubContext) -> str:
    """Return the stub text for the ``.py`` / ``.pyx`` file or extension module at *path*; nothing is written.

    The source is always harvested.  Unless ``ctx.config.imports`` is
    ``"none"``, the module is also imported (by its dotted name when it sits in a
    package) and live objects refine the source per symbol; an import
    failure falls back to the source with a WARNING.  An extension module
    (``.pyd`` / ``.so``) can only be imported and introspected.

    Parameters
    ----------
    path : str or pathlib.Path
        The module file to stub.
    ctx : StubContext
        Run state: configuration, diagnostics and the shared loader.

    Returns
    -------
    str
        The stub text.

    Raises
    ------
    FileNotFoundError
        If *path* is not a file.

    See Also
    --------
    stubpy.render : The public entry point that wraps this and catches failures.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> from stubpy.config import Config
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "mod.py"
    ...     _ = src.write_text("def f(x: int) -> str: ...\\n")
    ...     text = render_module(src, StubContext(config=Config(imports="none")))
    >>> print(text, end="")
    def f(x: int) -> str: ...
    """
    path = Path(path).resolve()
    if not vfs.is_file(path):
        raise FileNotFoundError(f"No such file: {path}")
    owns_loader = ctx.module_loader is None
    if owns_loader:
        ctx.module_loader = ModuleLoader(policy=ctx.config.import_policy)
    try:
        with introspection_cache():
            if is_extension_file(path):
                return render_compiled(path, ctx)
            if path.suffix == ".pyx":
                return render_cython_source(path, ctx)
            return _render(path, ctx)
    finally:
        if owns_loader:
            ctx.module_loader.close()
            ctx.module_loader = None


def _read_source(path: Path) -> str:
    """Read *path* honouring its encoding cookie and BOM."""
    return vfs.read_source(path)


def _parse(source: str, path: Path, ctx: StubContext) -> ast.Module | None:
    """Parse *source* once for every AST consumer; record an ERROR when it does not parse.

    Syntax from a newer Python than the running one raises :class:`NewerSyntaxError` instead.
    """
    try:
        return ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError) as exc:
        newer = required_python(source) if isinstance(exc, SyntaxError) else None
        if newer is not None:
            raise NewerSyntaxError(*newer) from exc
        ctx.diagnostics.error(
            Stage.AST_PASS, path.name,
            f"Source does not parse on this Python version: {type(exc).__name__}: {exc}",
        )
        return None


def _take_parsed(path: Path, source: str, ctx: StubContext) -> ParsedFile | None:
    """Pop what the run already parsed of *path* when it still matches *source*; a stale harvest is dropped."""
    parsed = ctx.source_index.parsed.pop(path, None) if ctx.source_index is not None else None
    if parsed is not None and parsed.digest != source_digest(source):
        ctx.source_index.forget(path)
        return None
    if parsed is None or ctx.source_index.harvested(path) is None:
        return None
    if parsed.version_test and ctx.config.version_branches is VersionBranches.EMIT:
        return None
    return parsed


def _render(path: Path, ctx: StubContext) -> str:
    """Return the stub text for *path*."""
    source = _read_source(path)
    parsed = _take_parsed(path, source, ctx)
    tree = None
    if parsed is None:
        tree = _parse(source, path, ctx)
        parsed = parsed_facts(source, tree) if tree is not None else None

    ast_symbols = _harvest(source, tree, parsed, path, ctx)
    if ast_symbols is not None and ast_symbols.skip_file:
        return ""

    module, module_name = _load(path, ctx) if parsed is not None else (None, f"{TARGET_MODULE_PREFIX}{_safe(path.stem)}")
    if module is not None:
        ctx.module_namespace = vars(module)
    if ast_symbols is not None:
        if ctx.source_index is None:
            ctx.source_index = SourceIndex()
        ctx.source_module = ctx.source_index.module_at(path)
    ctx.module_name = module_name
    _record_all(ast_symbols, module, path, ctx)
    _record_stars(ast_symbols, module, path, ctx)

    import_map = dict(parsed.import_map) if parsed is not None else {}
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
        lazy = lazy_reexports(parsed.lazy if parsed is not None else None, module, ast_symbols, ctx)

    body = emit_body(module, module_name, ctx)
    exports = reexport_lines(ast_symbols, ctx, is_package=path.name == "__init__.py") if ast_symbols else []
    exports += [line for line in lazy if line not in exports]
    header = "\n".join(build_header(body, ctx, module, module_name, import_map, exports, branch_bound))
    return stub_text(header, all_block(ctx.all_order, header, body), body)


def _load(path: Path, ctx: StubContext) -> tuple[_builtin_types.ModuleType | None, str]:
    """Import the module as the import policy allows; ``(None, name)`` means source analysis only."""
    module_name = f"{TARGET_MODULE_PREFIX}{_safe(path.stem)}"
    if not ctx.config.may_import:
        ctx.diagnostics.info(Stage.LOAD, path.name, "imports is 'none': module execution skipped")
        return None, module_name
    try:
        loaded = ctx.module_loader.load(path, ctx.diagnostics)
    except FileNotFoundError:
        raise
    except ImportBlockedError as exc:
        ctx.diagnostics.info(Stage.LOAD, path.name, f"Import {exc}; stubbing from the source")
        return None, module_name
    except ModuleReplacedError as exc:
        ctx.diagnostics.warning(Stage.LOAD, path.name, f"{IMPORT_FAILED_PREFIX}: {exc}; stubbing from the source instead")
        return None, module_name
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        ctx.diagnostics.warning(
            Stage.LOAD, path.name,
            f"{IMPORT_FAILED_PREFIX}, falling back to source analysis: {describe_load_error(exc)}",
        )
        return None, module_name
    return _probed(loaded.module, path, ctx), loaded.name


def _probed(module: _builtin_types.ModuleType, path: Path, ctx: StubContext) -> _builtin_types.ModuleType:
    """*module*, or a copy without the values that raise when inspected (lazy settings, context proxies).

    Those names are stubbed from the source; the imported module itself is never changed.
    """
    broken = [name for name, value in list(vars(module).items()) if not _inspectable(value)]
    if not broken:
        return module
    ctx.diagnostics.info(Stage.LOAD, path.name, f"Stubbed from the source because they raise when inspected: "
                                                f"{', '.join(broken)}")
    view = _builtin_types.ModuleType(module.__name__, module.__doc__)
    view.__dict__.update((k, v) for k, v in vars(module).items() if k not in broken)
    return view


def _inspectable(value: object) -> bool:
    """True when the attribute probes stubpy makes on *value* do not raise."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            isinstance(value, type)
            callable(value)
            for attr in ("__module__", "__args__", "__origin__", "__wrapped__", "__doc__"):
                getattr(value, attr, None)
    except KeyboardInterrupt:
        raise
    except BaseException:
        return False
    return True


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


def _harvest(
    source: str, tree: ast.Module | None, parsed: ParsedFile | None, path: Path, ctx: StubContext,
) -> ASTSymbols | None:
    """Run the AST pre-pass on the parsed *tree*, or reuse the run's harvest; ``None`` if the pass fails."""
    try:
        branches = ctx.config.version_branches is VersionBranches.EMIT
        reusable = parsed is not None and ctx.source_index is not None and not (branches and parsed.version_test)
        cached = ctx.source_index.harvested(path) if reusable else None
        ast_symbols = cached if cached is not None else ast_harvest(source, tree=tree, version_branches=branches)
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


def _safe(stem: str) -> str:
    """*stem* with every character that cannot appear in a module name replaced by ``_``."""
    return re.sub(r"\W", "_", stem)
