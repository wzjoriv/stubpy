"""
The public entry points: :func:`render`, :func:`generate` and :func:`check`.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path

from stubpy.analysis.loader import ModuleLoader
from stubpy.analysis.syntax import NewerSyntaxError
from stubpy.config.options import Config
from stubpy.resolve import introspection_cache
from stubpy.resolve.static import SourceIndex
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Stage

from ._cache import RunCache
from ._compiled import ExtensionImportError
from ._output import _dotted_name, _finish, _keeps_handwritten, _kept, _merged, _placeholder
from ._requested import requested_names
from ._submodules import package_layout
from .pipeline import render_module
from .results import Report, StubResult
from .targets import Job, TargetSpec, module_file_and_member, plan_jobs, resolve_targets


def render(target: TargetSpec, *, config: Config | None = None) -> StubResult:
    """Build the stub of one module without writing anything.

    Parameters
    ----------
    target : str or os.PathLike
        A ``.py`` file, an extension module (``.pyd`` / ``.so``), a package
        folder (its ``__init__.py`` is used), a glob matching exactly one
        file, or a dotted module name such as ``"mypkg.core"`` or
        ``"mypkg._native"``.
    config : Config, optional
        Run options; defaults to ``Config()``.

    Returns
    -------
    StubResult
        The stub text and diagnostics.  A module that fails to load gives a
        result with ``ok == False`` and an ERROR diagnostic instead of
        raising.

    Raises
    ------
    FileNotFoundError
        If *target* names no existing file, folder or module.
    ValueError
        If *target* is ambiguous, is not a Python module, or is a built-in
        module without a file.

    See Also
    --------
    generate : Write the stubs of several modules.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "mod.py"
    ...     _ = src.write_text("def f(x: int) -> str: ...\\n")
    ...     result = render(src, config=Config(imports="none"))
    >>> result.ok
    True
    >>> print(result.text, end="")
    def f(x: int) -> str: ...
    """
    cfg = config or Config()
    path, member = module_file_and_member(target)
    return _render(path, StubContext(config=cfg, submodule=member), None)


def generate(
    target: TargetSpec | Iterable[TargetSpec] | None = None,
    output: str | os.PathLike[str] | None = None,
    *,
    config: Config | None = None,
) -> Report:
    """Write ``.pyi`` stubs for files, folders, globs or modules.

    Parameters
    ----------
    target : str, os.PathLike, iterable of those, or None
        What to stub: ``.py`` files, extension modules (``.pyd`` / ``.so``),
        folders (searched recursively, extension modules included), glob
        patterns (``"src/**/*.py"``) or dotted module names.  ``None`` uses
        the config's ``targets`` and ``modules``.  An extension module found
        in a folder that cannot be imported (not built for this
        interpreter) gets a WARNING and no stub; named directly, it fails.
    output : str or os.PathLike, optional
        Where stubs go.  A path ending in ``.pyi`` is the stub of a single
        file target.  Any other path is a stub root: each module lands at
        its import path beneath it (``src/mypkg/core.py`` becomes
        ``<output>/mypkg/core.pyi``) and every package gets an
        ``__init__.pyi``.  Defaults to ``config.output_dir``, and without
        that each stub goes next to its source; there, an existing stub of
        an extension module is kept (it is often hand-written) unless
        ``incremental`` is on.
    config : Config, optional
        Run options; defaults to ``Config()``.  With ``incremental=True``
        the stub is merged into the existing file.

    Returns
    -------
    Report
        One :class:`StubResult` per module.  Modules that fail are listed in
        ``report.failed`` and not written; the rest of the run continues.

    Raises
    ------
    FileNotFoundError
        If a target names no existing file, folder or module.
    ValueError
        If a target is not Python source, *output* ends in ``.pyi`` with
        several targets, or no target is given or configured.

    See Also
    --------
    check : Compare the stubs on disk without writing.
    render : Build the stub of one module in memory.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "mod.py"
    ...     _ = src.write_text("def f(x: int) -> str: ...\\n")
    ...     report = generate(src, pathlib.Path(folder) / "stubs", config=Config(imports="none"))
    ...     written = [p.name for p in report.written]
    >>> print(report.summary())
    Generated 1 stub, 0 failed.
    >>> written
    ['mod.pyi']
    """
    return _run(target, output, config, "generate")


def check(
    target: TargetSpec | Iterable[TargetSpec] | None = None,
    output: str | os.PathLike[str] | None = None,
    *,
    config: Config | None = None,
) -> Report:
    """Compare the stubs on disk with what :func:`generate` would write.

    Nothing is written, so this suits CI and pre-commit hooks.

    Parameters
    ----------
    target : str, os.PathLike, iterable of those, or None, optional
        What to check; as for :func:`generate`.
    output : str or os.PathLike, optional
        Where the stubs live; as for :func:`generate`.
    config : Config, optional
        Run options; defaults to ``Config()``.

    Returns
    -------
    Report
        ``report.stale`` lists the stub paths that are missing or differ;
        ``report.ok`` is ``True`` when none are stale and none failed.

    Raises
    ------
    FileNotFoundError, ValueError
        As for :func:`generate`.

    See Also
    --------
    generate : Write the stubs.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "mod.py"
    ...     _ = src.write_text("def f(x: int) -> str: ...\\n")
    ...     stubs = pathlib.Path(folder) / "stubs"
    ...     before = check(src, stubs, config=Config(imports="none"))
    ...     _ = generate(src, stubs, config=Config(imports="none"))
    ...     after = check(src, stubs, config=Config(imports="none"))
    >>> before.ok, after.ok
    (False, True)
    >>> print(after.summary())
    Checked 1 stub: 0 stale, 0 failed.
    """
    return _run(target, output, config, "check")


def _run(
    target: TargetSpec | Iterable[TargetSpec] | None,
    output: str | os.PathLike[str] | None,
    config: Config | None,
    action: str,
) -> Report:
    """Resolve the targets, stub every module, then write or compare."""
    cfg = config or Config()
    out = output if output is not None else cfg.output_dir
    plan = plan_jobs(resolve_targets(target, cfg), out, cfg)
    single = out is not None and Path(out).suffix == ".pyi"
    report = Report(action=action, strict=cfg.strict, excluded=list(plan.excluded))
    cache = RunCache(Path(cfg.cache_dir), cfg) if cfg.cache else None
    for root, jobs in plan.groups:
        index = SourceIndex()
        requested = requested_names((job.source for job in jobs), index)
        modules = {_dotted_name(job.source): job.source for job in jobs if job.source.suffix == ".py"}
        with ModuleLoader(root, policy=cfg.import_policy) as loader, introspection_cache():
            queue = list(jobs)
            while queue:
                job = queue.pop(0)
                if _keeps_handwritten(job, out, cfg):
                    _finish(_kept(job), report)
                    continue
                ctx = StubContext(config=cfg, module_loader=loader, source_index=index, submodule=job.member)
                ctx.requested_names = requested.get(job.source.resolve(), set())
                key = None
                if cache is not None and job.source.suffix == ".py" and not job.member:
                    key = cache.key(job.source, modules) + "|" + ",".join(sorted(ctx.requested_names))
                    cached = cache.get(job.source, key, job.output)
                    if cached is not None:
                        _finish(_merged(cached, cfg), report, raw=cfg.incremental)
                        continue
                result = _render(job.source, ctx, job.output, explicit=job.explicit)
                if key is not None and not ctx.submodules:
                    cache.put(key, result)  # type: ignore[union-attr]
                if ctx.submodules and result.ok and result.output is not None and not single:
                    result, children = package_layout(result, job.member, ctx.submodules)
                    queue[:0] = [Job(job.source, stub, job.explicit, member) for member, stub in children]
                _finish(_merged(result, cfg), report, raw=cfg.incremental)
    for job in plan.placeholders:
        if not job.output.exists():
            _finish(_placeholder(job), report)
    if cache is not None:
        cache.save()
    return report


def _render(path: Path, ctx: StubContext, output: Path | None, explicit: bool = True) -> StubResult:
    """Render *path*, turning a raised exception into an ERROR diagnostic.

    An extension module that cannot be imported is only a WARNING (and gets
    no stub) when it was found in a folder rather than named directly.
    """
    text = ""
    try:
        text = render_module(path, ctx)
    except NewerSyntaxError as exc:
        running = ".".join(map(str, sys.version_info[:2]))
        ctx.diagnostics.warning(Stage.AST_PASS, path.name, f"Skipped: the source {exc}; this is Python {running}. "
                                "Run stubpy on that version or newer to stub it")
        output = None
    except ExtensionImportError as exc:
        report = ctx.diagnostics.error if explicit else ctx.diagnostics.warning
        report(Stage.LOAD, path.name, f"{exc}; no stub written" if not explicit else str(exc))
        if not explicit:
            output = None
    except (Exception, SystemExit) as exc:
        if not ctx.diagnostics.has_errors():
            ctx.diagnostics.error(Stage.GENERATOR, path.name, f"{type(exc).__name__}: {exc}")
    return StubResult(
        text=text,
        diagnostics=tuple(ctx.diagnostics),
        source=path,
        module_name=ctx.module_name or _dotted_name(path),
        output=output,
    )
