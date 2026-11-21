"""
Stub rendering for a compiled extension module: import, introspect, emit through the AST-only emitters.
"""
from __future__ import annotations

import types
from pathlib import Path

from stubpy.analysis import vfs
from stubpy.analysis.loader import ModuleLoadError, describe_load_error, find_import_target
from stubpy.compiled.capi import source_module
from stubpy.compiled.detect import is_current_abi, is_extension_file, module_stem
from stubpy.compiled.introspect import build_compiled_table
from stubpy.compiled.pyx import synthetic_module
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Stage

from ._body import emit_body
from ._layout import all_block, stub_text
from ._submodules import attribute_submodules
from .header import build_header


class ExtensionImportError(ModuleLoadError):
    """Raised when an extension module cannot be imported (not built for this interpreter, missing DLL, imports off)."""


def render_compiled(path: Path, ctx: StubContext) -> str:
    """Return the stub text of the extension module at *path*; raises :exc:`ExtensionImportError` when it cannot load."""
    if not ctx.config.may_import:
        fallback = _from_c(path, ctx, "imports is 'none'")
        if fallback is not None:
            return fallback
        raise ExtensionImportError("imports is 'none': a compiled module can only be stubbed by importing it")
    if not vfs.is_file(path):
        raise FileNotFoundError(f"No such file: {path}")
    try:
        loaded = ctx.module_loader.load(path, ctx.diagnostics)
    except Exception as exc:
        source = path.with_name(module_stem(path) + ".pyx")
        if source.is_file():
            ctx.diagnostics.warning(Stage.LOAD, path.name, f"Cannot import extension module: {describe_load_error(exc)}; "
                                                         f"stubbing from {source.name} instead")
            return _from_source(source, ctx)
        fallback = _from_c(path, ctx, f"Cannot import extension module: {describe_load_error(exc)}")
        if fallback is not None:
            return fallback
        raise ExtensionImportError(f"Cannot import extension module: {describe_load_error(exc)}", exc) from exc
    ctx.diagnostics.info(Stage.LOAD, path.name, f"Compiled module {loaded.name} imported from {path.name}")
    module = loaded.module
    for part in filter(None, ctx.submodule.split(".")):
        child = getattr(module, part, None)
        if not isinstance(child, types.ModuleType):
            raise ExtensionImportError(f"{module.__name__} has no submodule {part!r}")
        module = child
    return render_live_module(module, ctx)


def _from_c(path: Path, ctx: StubContext, why: str) -> str | None:
    """The stub of *path* built from its C sources alone, with a WARNING saying *why*; ``None`` without C sources."""
    target = find_import_target(path)
    module = source_module(path, target.name if target is not None else module_stem(path))
    if module is None:
        return None
    ctx.diagnostics.warning(Stage.LOAD, path.name, f"{why}; stubbing from its C sources instead")
    return render_live_module(module, ctx)


def render_live_module(module: types.ModuleType, ctx: StubContext) -> str:
    """Return the stub text of an imported compiled *module*, introspected through its symbol table."""
    name = module.__name__
    ctx.module_name = name
    ctx.module_namespace = vars(module)
    cfg = ctx.config
    built = build_compiled_table(
        module, diagnostics=ctx.diagnostics, include_private=cfg.include_private,
        include_docstrings=cfg.include_docstrings, respect_all=cfg.respect_all,
        array_metadata=cfg.array_metadata,
    )
    ctx.symbol_table = built.table
    ctx.extra_imports.update(built.imports)
    if built.all_names is not None:
        ctx.all_exports = set(built.all_names)
        ctx.all_order = list(dict.fromkeys(built.all_names))
    ctx.submodules = attribute_submodules(module)
    body = emit_body(None, name, ctx)
    reexports = [f"from . import {child} as {child}" for child in ctx.submodules]
    header = "\n".join(build_header(body, ctx, None, name, {}, reexports))
    return stub_text(header, all_block(ctx.all_order, header, body), body)


def render_cython_source(path: Path, ctx: StubContext) -> str:
    """Return the stub of the Cython source *path*: through its built module when one imports, else from the source.

    A built module is introspected with the ``.pyx`` filling the types and
    defaults it lacks; an unbuilt one is stubbed from the ``.pyx`` alone.
    """
    built = next((p for p in sorted(path.parent.iterdir()) if is_extension_file(p) and is_current_abi(p)
                  and module_stem(p) == path.stem), None)
    if built is not None and ctx.config.may_import:
        try:
            return render_compiled(built, ctx)
        except ExtensionImportError as exc:
            ctx.diagnostics.warning(Stage.LOAD, path.name, f"{exc}; stubbing from the Cython source instead")
    return _from_source(path, ctx)


def _from_source(path: Path, ctx: StubContext) -> str:
    """The stub of the Cython source *path* alone, through a stand-in module."""
    target = find_import_target(path)
    name = target.name if target is not None else path.stem
    ctx.diagnostics.info(Stage.LOAD, path.name, "Stubbed from the Cython source; no build of it was imported")
    return render_live_module(synthetic_module(path, name), ctx)
