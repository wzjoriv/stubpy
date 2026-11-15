"""Stub rendering for a compiled extension module: import, introspect, emit through the AST-only emitters."""
from __future__ import annotations

import types
from pathlib import Path

from stubpy.analysis.loader import ModuleLoadError, describe_load_error
from stubpy.compiled.introspect import build_compiled_table
from stubpy.config.options import Mode

from ._body import emit_body
from ._layout import all_block, stub_text
from .context import StubContext
from .diagnostics import Stage
from .header import build_header


class ExtensionImportError(ModuleLoadError):
    """Raised when an extension module cannot be imported (not built for this interpreter, missing DLL, AST mode)."""


def render_compiled(path: Path, ctx: StubContext) -> str:
    """Return the stub text of the extension module at *path*; raises :exc:`ExtensionImportError` when it cannot load."""
    if ctx.config.mode is Mode.AST:
        raise ExtensionImportError("AST mode: a compiled module can only be stubbed by importing it")
    try:
        loaded = ctx.module_loader.load(path, ctx.diagnostics)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ExtensionImportError(f"Cannot import extension module: {describe_load_error(exc)}", exc) from exc
    ctx.diagnostics.info(Stage.LOAD, path.name, f"Compiled module {loaded.name} imported from {path.name}")
    return render_live_module(loaded.module, ctx)


def render_live_module(module: types.ModuleType, ctx: StubContext) -> str:
    """Return the stub text of an imported compiled *module*, introspected through its symbol table."""
    name = module.__name__
    ctx.module_name = name
    ctx.module_namespace = vars(module)
    cfg = ctx.config
    built = build_compiled_table(
        module, diagnostics=ctx.diagnostics, include_private=cfg.include_private,
        include_docstrings=cfg.include_docstrings, respect_all=cfg.respect_all,
    )
    ctx.symbol_table = built.table
    ctx.extra_imports.update(built.imports)
    if built.all_names is not None:
        ctx.all_exports = set(built.all_names)
        ctx.all_order = list(dict.fromkeys(built.all_names))
    body = emit_body(None, name, ctx)
    header = "\n".join(build_header(body, ctx, None, name, {}, []))
    return stub_text(header, all_block(ctx.all_order, header, body), body)
