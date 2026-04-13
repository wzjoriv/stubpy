"""
stubpy.__main__
===============

CLI entry point — invoked via ``python -m stubpy`` or the ``stubpy``
console script installed by ``pip install stubpy``.

Usage::

    # Single file
    stubpy path/to/module.py
    stubpy path/to/module.py -o path/to/module.pyi
    stubpy path/to/module.py --print

    # Multiple files — stubs written alongside each source
    stubpy a.py b.py c.py
    stubpy "src/*.py"          # quoted glob (Python-level expansion)
    stubpy module.py mypkg/   # mix files and directories

    # Whole package (directory)
    stubpy path/to/package/
    stubpy path/to/package/ -o stubs/

    # Common flags
    stubpy module.py --include-private
    stubpy module.py --include-docstrings
    stubpy module.py --verbose --strict
    stubpy module.py --union-style modern
    stubpy module.py --execution-mode ast_only

Configuration
-------------
stubpy searches upward from the first given path for a ``stubpy.toml``
file or a ``[tool.stubpy]`` section in ``pyproject.toml``.  CLI flags
always override file values.
"""
from __future__ import annotations

import argparse
import glob as _glob
import sys
from pathlib import Path

from . import generate_stub
from .config import load_config
from .context import ExecutionMode, StubConfig, StubContext
from .generator import generate_package

_MODE_MAP: dict[str, ExecutionMode] = {
    "runtime":  ExecutionMode.RUNTIME,
    "ast_only": ExecutionMode.AST_ONLY,
    "auto":     ExecutionMode.AUTO,
}


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``stubpy`` command-line interface.

    Parameters
    ----------
    argv : list[str], optional
        Argument list to parse.  When ``None`` (default), ``sys.argv[1:]``
        is used.

    Returns
    -------
    int
        ``0`` on success; ``1`` on any error or (with ``--strict``) on any
        ERROR-level diagnostic.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    targets = _expand_paths(args.paths)
    if not targets:
        print("Error: no files matched the given path(s) or pattern(s).", file=sys.stderr)
        return 1

    cfg = _build_config(args)

    if len(targets) == 1:
        t = targets[0]
        return _run_package(t, args, cfg) if t.is_dir() else _run_file(t, args, cfg)
    return _run_multi(targets, args, cfg)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stubpy",
        description=(
            "Generate .pyi stub files for Python source files or package "
            "directories, with full **kwargs / *args backtracing."
        ),
    )
    p.add_argument(
        "paths",
        nargs="+",
        metavar="path",
        help=(
            "One or more .py files, package directories, or quoted glob "
            'patterns (e.g. "src/*.py").  Directories are processed '
            "recursively.  When multiple paths are given, -o is ignored."
        ),
    )
    p.add_argument(
        "-o", "--output",
        metavar="PATH",
        help=(
            "Output path.  For a single file: the .pyi file to write.  "
            "For a directory: the root output directory.  Defaults to "
            "alongside the source.  Ignored when multiple paths are given."
        ),
    )
    p.add_argument(
        "--print",
        action="store_true",
        help="Print the generated stub to stdout (single-file mode only).",
    )
    p.add_argument(
        "--include-private",
        action="store_true",
        help="Include symbols whose names start with '_'.",
    )
    p.add_argument(
        "--include-docstrings",
        action="store_true",
        help=(
            "Embed each symbol's docstring as a triple-quoted string body "
            "instead of '...'.  Useful when stubs double as documentation."
        ),
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print INFO / WARNING / ERROR diagnostics to stderr.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any ERROR diagnostic was recorded.",
    )
    p.add_argument(
        "--execution-mode",
        metavar="MODE",
        choices=["runtime", "ast_only", "auto"],
        help=(
            "'runtime' (default): execute the module.  "
            "'ast_only': parse only, no import.  "
            "'auto': runtime with AST-only fallback."
        ),
    )
    p.add_argument(
        "--union-style",
        metavar="STYLE",
        choices=["modern", "legacy"],
        help=(
            "'modern' (default, PEP 604): emits str | None.  "
            "'legacy': emits Optional[str]."
        ),
    )
    p.add_argument(
        "--alias-style",
        metavar="STYLE",
        choices=["compatible", "pep695", "auto"],
        help=(
            "'compatible' (default): Name: TypeAlias = rhs.  "
            "'pep695': type Name = rhs (Python 3.12+).  "
            "'auto': selects based on runtime Python version."
        ),
    )
    p.add_argument(
        "--infer-types",
        action="store_true",
        help=(
            "Infer parameter/return types from NumPy, Google, or Sphinx "
            "docstrings for unannotated functions.  Types emitted as "
            "'# type:' comments to distinguish them from real annotations."
        ),
    )
    p.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "Wrap generated stub in '# stubpy: auto-generated begin/end' "
            "markers and merge into existing .pyi, preserving manual edits "
            "outside the markers."
        ),
    )
    p.add_argument(
        "--exclude",
        metavar="PATTERN",
        action="append",
        default=[],
        dest="exclude",
        help=(
            "Glob pattern for files to skip during package processing "
            "(e.g. '**/test_*.py').  May be repeated for multiple patterns: "
            "--exclude '**/migrations/*' --exclude 'setup.py'."
        ),
    )
    p.add_argument(
        "--no-respect-all",
        action="store_true",
        help=(
            "Stub all public symbols even if __all__ is defined.  "
            "By default (without this flag) only names listed in __all__ "
            "are stubbed when __all__ is present."
        ),
    )
    p.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore stubpy.toml and pyproject.toml [tool.stubpy].",
    )
    return p


# ---------------------------------------------------------------------------
# Path expansion (glob support)
# ---------------------------------------------------------------------------

def _expand_paths(raw_paths: list[str]) -> list[Path]:
    """Expand glob patterns in *raw_paths* and return concrete :class:`Path` objects.

    Patterns containing ``*``, ``?``, or ``[`` are passed to
    :func:`glob.glob` with ``recursive=True`` so that ``**`` works across
    directory trees.  Explicit paths with no wildcard characters pass
    through unchanged.

    Parameters
    ----------
    raw_paths : list[str]
        Raw path strings from the argument parser.

    Returns
    -------
    list[Path]
        Deduplicated, ordered list of resolved paths.  An empty list means
        nothing matched — callers should report an error and exit 1.
    """
    seen: set[str] = set()
    result: list[Path] = []

    for raw in raw_paths:
        if any(c in raw for c in ("*", "?", "[")):
            matches = sorted(_glob.glob(raw, recursive=True))
            if not matches:
                print(f"Warning: glob pattern matched no files: {raw!r}", file=sys.stderr)
            for m in matches:
                if m not in seen:
                    seen.add(m)
                    result.append(Path(m))
        else:
            if raw not in seen:
                seen.add(raw)
                result.append(Path(raw))

    return result


# ---------------------------------------------------------------------------
# Config assembly
# ---------------------------------------------------------------------------

def _build_config(args: argparse.Namespace) -> StubConfig:
    """Merge file-level config with CLI overrides into a :class:`StubConfig`."""
    first = Path(args.paths[0])
    if args.no_config:
        file_cfg = StubConfig()
    else:
        search_dir = first if first.is_dir() else first.parent
        file_cfg = load_config(search_dir)

    return StubConfig(
        include_private    = args.include_private    or file_cfg.include_private,
        include_docstrings = getattr(args, "include_docstrings", False) or file_cfg.include_docstrings,
        verbose            = args.verbose            or file_cfg.verbose,
        strict             = args.strict             or file_cfg.strict,
        union_style        = getattr(args, "union_style",   None) or file_cfg.union_style,
        alias_style        = getattr(args, "alias_style",   None) or file_cfg.alias_style,
        exclude            = list(file_cfg.exclude) + list(getattr(args, "exclude", []) or []),
        output_dir         = file_cfg.output_dir,
        execution_mode     = _MODE_MAP.get(args.execution_mode or "", file_cfg.execution_mode),
        respect_all        = False if getattr(args, "no_respect_all", False) else file_cfg.respect_all,
        infer_types_from_docstrings = (
            getattr(args, "infer_types", False) or file_cfg.infer_types_from_docstrings
        ),
        incremental_update = (
            getattr(args, "incremental", False) or file_cfg.incremental_update
        ),
    )


# ---------------------------------------------------------------------------
# Dispatch modes
# ---------------------------------------------------------------------------

def _run_file(target: Path, args: argparse.Namespace, cfg: StubConfig) -> int:
    """Generate a stub for a single ``.py`` file."""
    ctx = StubContext(config=cfg)
    try:
        content = generate_stub(str(target), getattr(args, "output", None), ctx=ctx)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:          # pragma: no cover
        print(f"Error generating stub: {exc}", file=sys.stderr)
        return 1

    out_path = getattr(args, "output", None) or str(target.with_suffix(".pyi"))
    print(f"Stub written to: {out_path}")

    if cfg.verbose and ctx.diagnostics:
        print("\n--- Diagnostics ---", file=sys.stderr)
        for d in ctx.diagnostics:
            print(f"  {d}", file=sys.stderr)
        print(f"  Summary: {ctx.diagnostics.summary()}", file=sys.stderr)

    if cfg.strict and ctx.diagnostics.has_errors():
        n = len(ctx.diagnostics.errors)
        print(f"\nStub generation completed with {n} error(s). Exiting 1 (--strict).", file=sys.stderr)
        return 1

    if getattr(args, "print", False):
        print("\n--- Generated stub ---\n")
        print(content)

    return 0


def _run_package(target: Path, args: argparse.Namespace, cfg: StubConfig) -> int:
    """Generate stubs for all ``.py`` files under a package directory."""
    output_dir = getattr(args, "output", None) or cfg.output_dir
    print(f"Processing package: {target}")
    print(f"Output directory:  {output_dir}" if output_dir else "Output: alongside source files")

    try:
        result = generate_package(
            str(target),
            output_dir=output_dir,
            ctx_factory=lambda: StubContext(config=cfg),
            config=cfg,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:          # pragma: no cover
        print(f"Error processing package: {exc}", file=sys.stderr)
        return 1

    print(f"\n{result.summary()}")

    if result.failed:
        print("\nFailed files:", file=sys.stderr)
        for path, diags in result.failed:
            print(f"  {path}", file=sys.stderr)
            for d in diags:
                print(f"    {d}", file=sys.stderr)

    if cfg.strict and result.failed:
        print(
            f"\nPackage processing completed with {len(result.failed)} failed file(s). Exiting 1 (--strict).",
            file=sys.stderr,
        )
        return 1

    return 0


def _run_multi(targets: list[Path], args: argparse.Namespace, cfg: StubConfig) -> int:
    """Process two or more paths — files, directories, or a mix.

    The ``-o`` / ``--output`` flag is silently suppressed in this mode;
    each stub is written alongside its source.
    """
    if getattr(args, "output", None):
        print(
            "Warning: -o/--output is ignored when multiple paths are given; "
            "stubs are written alongside each source.",
            file=sys.stderr,
        )

    # Build a namespace without 'output' so _run_file / _run_package don't see it
    inner = argparse.Namespace(**{**vars(args), "output": None})

    any_error = False
    for target in targets:
        rc = _run_package(target, inner, cfg) if target.is_dir() else _run_file(target, inner, cfg)
        if rc != 0:
            any_error = True

    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
