"""Package-wide stub generation."""
from __future__ import annotations

import fnmatch
import inspect
from collections.abc import Callable
from pathlib import Path

from stubpy._constants import INIT_PYI_PLACEHOLDER
from stubpy.config.options import StubConfig

from .context import StubContext
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

    Files matching ``config.exclude`` are skipped.  A file that raises or
    records ERROR diagnostics is listed in :attr:`PackageResult.failed`
    and processing continues.  With *output_dir*, every sub-package also
    gets an ``__init__.pyi``.

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

    for py_file in sorted(pkg_root.rglob("*.py")):
        rel = py_file.relative_to(pkg_root)
        if any(fnmatch.fnmatch(rel.as_posix(), pat) for pat in exclude_patterns):
            continue

        out_path: str | None = None
        if out_root is not None:
            out_pyi = out_root / rel.with_suffix(".pyi")
            out_pyi.parent.mkdir(parents=True, exist_ok=True)
            out_path = str(out_pyi)
        written = Path(out_path) if out_path else py_file.with_suffix(".pyi")

        if ctx_factory is not None:
            ctx = _call_factory(ctx_factory, py_file, written)
        else:
            ctx = StubContext(config=effective_config)

        try:
            generate_stub(str(py_file), out_path, ctx=ctx)
            if not ctx.diagnostics.has_errors():
                result.stubs_written.append(written)
            else:
                result.failed.append((py_file, ctx.diagnostics.errors))
        except Exception:
            result.failed.append((py_file, ctx.diagnostics.errors))

    if out_root is not None:
        _ensure_init_pyi(pkg_root, out_root)

    return result


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
