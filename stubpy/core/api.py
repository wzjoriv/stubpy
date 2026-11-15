"""The public entry points: :func:`render`, :func:`generate` and :func:`check`."""
from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from stubpy._constants import INIT_PYI_PLACEHOLDER
from stubpy.analysis.loader import ModuleLoader, find_import_target
from stubpy.config.options import Config
from stubpy.merge import read_and_merge
from stubpy.resolve import introspection_cache

from .context import StubContext
from .diagnostics import Diagnostic, Level, Stage
from .pipeline import render_module
from .results import Report, StubResult
from .targets import Job, TargetSpec, plan_jobs, resolve_module_file, resolve_targets


def render(target: TargetSpec, *, config: Config | None = None) -> StubResult:
    """Build the stub of one module without writing anything.

    Parameters
    ----------
    target : str or os.PathLike
        A ``.py`` file, a package folder (its ``__init__.py`` is used), a
        glob matching exactly one file, or a dotted module name such as
        ``"mypkg.core"``.
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
        If *target* is ambiguous or is not a Python module.

    Examples
    --------
    >>> import stubpy
    >>> print(stubpy.render("mymodule.py").text)  # doctest: +SKIP
    >>> stubpy.render("mypkg.core", config=stubpy.Config(mode="ast")).ok  # doctest: +SKIP
    True
    """
    cfg = config or Config()
    path = resolve_module_file(target)
    return _render(path, StubContext(config=cfg), None)


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
        What to stub: ``.py`` files, folders (searched recursively), glob
        patterns (``"src/**/*.py"``) or dotted module names.  ``None`` uses
        the config's ``targets`` and ``modules``.
    output : str or os.PathLike, optional
        Where stubs go.  A path ending in ``.pyi`` is the stub of a single
        file target.  Any other path is a stub root: each module lands at
        its import path beneath it (``src/mypkg/core.py`` becomes
        ``<output>/mypkg/core.pyi``) and every package gets an
        ``__init__.pyi``.  Defaults to ``config.output_dir``, and without
        that each stub goes next to its source.
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

    Examples
    --------
    >>> import stubpy
    >>> report = stubpy.generate("src/mypkg", "stubs")  # doctest: +SKIP
    >>> print(report.summary())  # doctest: +SKIP
    Generated 8 stubs, 0 failed.
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
    target, output, config
        As for :func:`generate`.

    Returns
    -------
    Report
        ``report.stale`` lists the stub paths that are missing or differ;
        ``report.ok`` is ``True`` when none are stale and none failed.

    Raises
    ------
    FileNotFoundError, ValueError
        As for :func:`generate`.

    Examples
    --------
    >>> import stubpy
    >>> report = stubpy.check("src/mypkg", "stubs")  # doctest: +SKIP
    >>> if not report.ok:  # doctest: +SKIP
    ...     raise SystemExit(report.summary())
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
    plan = plan_jobs(resolve_targets(target, cfg), output if output is not None else cfg.output_dir, cfg)
    report = Report(action=action, strict=cfg.strict)
    for root, jobs in plan.groups:
        with ModuleLoader(root) as loader, introspection_cache():
            for job in jobs:
                result = _render(job.source, StubContext(config=cfg, module_loader=loader), job.output)
                _finish(_merged(result, cfg), report)
    for job in plan.placeholders:
        if not job.output.exists():
            _finish(_placeholder(job), report)
    return report


def _render(path: Path, ctx: StubContext, output: Path | None) -> StubResult:
    """Render *path*, turning a raised exception into an ERROR diagnostic."""
    text = ""
    try:
        text = render_module(path, ctx)
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


def _merged(result: StubResult, cfg: Config) -> StubResult:
    """Return *result* with its text merged into the existing stub when ``incremental`` is on."""
    if not cfg.incremental or not result.ok or result.output is None:
        return result
    text, warning = read_and_merge(result.output, result.text)
    name = result.source.name if result.source else ""
    if warning is not None:
        note = Diagnostic(Level.WARNING, Stage.GENERATOR, name, str(warning))
    else:
        note = Diagnostic(Level.INFO, Stage.GENERATOR, name, "Incremental update: merged with the existing stub")
    return replace(result, text=text, diagnostics=(*result.diagnostics, note))


def _placeholder(job: Job) -> StubResult:
    """Return the result for a package folder's placeholder ``__init__.pyi``."""
    return StubResult(INIT_PYI_PLACEHOLDER, (), job.source, _dotted_name(job.source / "__init__.py"), job.output)


def _finish(result: StubResult, report: Report) -> None:
    """Record *result* and write its stub (``generate``) or compare it with the file on disk (``check``)."""
    report.results.append(result)
    if not result.ok or result.output is None:
        return
    if report.action == "check":
        existing = result.output.read_text(encoding="utf-8") if result.output.is_file() else None
        if existing != result.text:
            report.stale.append(result.output)
        return
    result.output.parent.mkdir(parents=True, exist_ok=True)
    result.output.write_text(result.text, encoding="utf-8")
    report.written.append(result.output)


def _dotted_name(path: Path) -> str:
    target = find_import_target(path)
    return target.name if target is not None else path.stem
