"""Package-wide stub generation."""
from __future__ import annotations

import fnmatch
import inspect
from collections.abc import Callable
from pathlib import Path

from stubpy._constants import INIT_PYI_PLACEHOLDER
from stubpy.analysis.loader import ModuleLoader
from stubpy.config.options import StubConfig
from stubpy.resolve import introspection_cache

from .context import StubContext
from .diagnostics import DiagnosticStage
from .pipeline import generate_stub
from .results import PackageResult

ContextFactory = Callable[[Path, Path], StubContext] | Callable[[], StubContext]


def generate_package(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
    ctx_factory: ContextFactory | None = None,
    config: StubConfig | None = None,
) -> PackageResult:
    """Generate ``.pyi`` stubs for every ``.py`` file under *package_dir*.

    Files matching ``config.exclude`` are skipped.  Each module is imported
    once per run, by its dotted name, and modules imported from the package
    are dropped from :data:`sys.modules` afterwards.  A file that raises or
    records ERROR diagnostics is listed in :attr:`PackageResult.failed`
    with the reason as an ERROR diagnostic, and processing continues.  With
    *output_dir*, every sub-package also gets an ``__init__.pyi``.

    Parameters
    ----------
    package_dir : str or Path
        Root of the package.
    output_dir : str or Path or None
        Where to mirror the package's stubs; ``None`` writes them alongside
        the sources.
    ctx_factory : callable or None
        Builds the :class:`~stubpy.StubContext` for each file, called as
        ``ctx_factory()`` or ``ctx_factory(source_path, output_path)``.
    config : StubConfig or None
        Configuration used when *ctx_factory* is ``None``.

    Returns
    -------
    PackageResult
        The written stubs and the failures.

    Raises
    ------
    FileNotFoundError
        If *package_dir* does not exist.

    Examples
    --------
    >>> from stubpy import generate_package
    >>> print(generate_package("mypackage/", "stubs/").summary())  # doctest: +SKIP
    Generated 8 stubs, 0 failed.
    """
    pkg_root = Path(package_dir).resolve()
    if not pkg_root.exists():
        raise FileNotFoundError(f"Package directory not found: {pkg_root}")

    out_root: Path | None = Path(output_dir).resolve() if output_dir else None
    effective_config = config or StubConfig()
    exclude_patterns: list[str] = list(effective_config.exclude or [])

    result = PackageResult()

    with ModuleLoader(pkg_root) as loader, introspection_cache():
        for py_file in sorted(pkg_root.rglob("*.py")):
            rel = py_file.relative_to(pkg_root)
            if any(fnmatch.fnmatch(rel.as_posix(), pat) for pat in exclude_patterns):
                continue
            _process_file(py_file, rel, out_root, ctx_factory, effective_config, loader, result)

    if out_root is not None:
        _ensure_init_pyi(pkg_root, out_root)

    return result


def _process_file(
    py_file: Path,
    rel: Path,
    out_root: Path | None,
    ctx_factory: ContextFactory | None,
    config: StubConfig,
    loader: ModuleLoader,
    result: PackageResult,
) -> None:
    """Stub one file of the package, recording it as written or failed in *result*."""
    out_path: str | None = None
    if out_root is not None:
        out_pyi = out_root / rel.with_suffix(".pyi")
        out_pyi.parent.mkdir(parents=True, exist_ok=True)
        out_path = str(out_pyi)
    written = Path(out_path) if out_path else py_file.with_suffix(".pyi")

    ctx = _call_factory(ctx_factory, py_file, written) if ctx_factory is not None else StubContext(config=config)
    if ctx.module_loader is None:
        ctx.module_loader = loader

    try:
        generate_stub(str(py_file), out_path, ctx=ctx)
    except (Exception, SystemExit) as exc:
        if not ctx.diagnostics.has_errors():
            ctx.diagnostics.error(DiagnosticStage.GENERATOR, py_file.name, f"{type(exc).__name__}: {exc}")
        result.failed.append((py_file, ctx.diagnostics.errors))
        return
    if ctx.diagnostics.has_errors():
        result.failed.append((py_file, ctx.diagnostics.errors))
    else:
        result.stubs_written.append(written)


def _call_factory(factory: ContextFactory, source: Path, output: Path) -> StubContext:
    """Call *factory* with ``(source, output)`` when it takes two required arguments, else with none."""
    try:
        sig = inspect.signature(factory)
        n_required = sum(
            1 for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        )
        if n_required >= 2:
            return factory(source, output)  # type: ignore[call-arg]
        return factory()  # type: ignore[call-arg]
    except (TypeError, ValueError):
        return factory()  # type: ignore[call-arg]


def _ensure_init_pyi(pkg_root: Path, out_root: Path) -> None:
    """Write a placeholder ``__init__.pyi`` for each sub-package that has none in *out_root*."""
    for init_py in pkg_root.rglob("__init__.py"):
        out_init = out_root / init_py.parent.relative_to(pkg_root) / "__init__.pyi"
        if not out_init.exists():
            out_init.parent.mkdir(parents=True, exist_ok=True)
            out_init.write_text(INIT_PYI_PLACEHOLDER, encoding="utf-8")
