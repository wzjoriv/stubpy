"""
stubpy.__main__
===============

CLI entry point — invoked via ``python -m stubpy`` or the ``stubpy``
console script installed by ``pip install stubpy``.

Usage::

    stubpy path/to/module.py
    stubpy path/to/module.py -o path/to/module.pyi
    stubpy path/to/module.py --print
    stubpy path/to/module.py --include-private
    stubpy path/to/module.py --verbose
    stubpy path/to/module.py --strict
    stubpy path/to/module.py --typing-style modern
    stubpy path/to/module.py --execution-mode ast_only

    stubpy path/to/package/              # whole package (directory mode)
    stubpy path/to/package/ -o stubs/    # package → custom output dir

Configuration file
------------------
When processing a package, stubpy searches upward from the given path for
a ``stubpy.toml`` file or a ``[tool.stubpy]`` section in ``pyproject.toml``.
Command-line flags override config file values.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import generate_stub
from .config import load_config
from .context import ExecutionMode, StubConfig, StubContext
from .generator import generate_package


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``stubpy`` command-line interface.

    Parameters
    ----------
    argv : list of str, optional
        Argument list to parse. Defaults to ``None`` (reads ``sys.argv``).

    Returns
    -------
    int
        ``0`` on success, ``1`` on any error or (with ``--strict``) any
        ERROR-level diagnostic.
    """
    parser = argparse.ArgumentParser(
        prog="stubpy",
        description=(
            "Generate .pyi stub files for a Python source file or package "
            "directory, with full **kwargs and *args backtracing through the "
            "class MRO."
        ),
    )
    parser.add_argument(
        "path",
        help=(
            "Python source file (.py) or package directory to stub. "
            "When a directory is given, all .py files are processed recursively."
        ),
    )
    parser.add_argument(
        "-o", "--output",
        metavar="PATH",
        help=(
            "Output path.  For a single file: the .pyi path to write.  "
            "For a directory: the root output directory for all stubs. "
            "Defaults to alongside the source (file mode) or the package "
            "directory itself (directory mode)."
        ),
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the generated stub to stdout after writing (file mode only).",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include symbols whose names start with '_'.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print all diagnostics (INFO, WARNING, ERROR) to stderr.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any ERROR-level diagnostic was recorded.",
    )
    parser.add_argument(
        "--execution-mode",
        metavar="MODE",
        choices=["runtime", "ast_only", "auto"],
        help=(
            "Module execution strategy: 'runtime' (default), 'ast_only' "
            "(no module execution), or 'auto' (runtime with fallback)."
        ),
    )
    parser.add_argument(
        "--typing-style",
        metavar="STYLE",
        choices=["modern", "legacy"],
        help=(
            "Output style for union annotations: 'modern' (PEP 604 str | None) "
            "or 'legacy' (Optional[str]).  Defaults to 'modern'."
        ),
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore any stubpy.toml / pyproject.toml [tool.stubpy] config file.",
    )

    args = parser.parse_args(argv)
    target = Path(args.path)

    # --- Load config from file (unless --no-config) -----------------------
    if args.no_config:
        file_cfg = StubConfig()
    else:
        search_dir = target if target.is_dir() else target.parent
        file_cfg = load_config(search_dir)

    # --- Apply CLI overrides on top of file config ------------------------
    cfg_kwargs: dict = {
        "include_private": file_cfg.include_private,
        "verbose":         file_cfg.verbose,
        "strict":          file_cfg.strict,
        "typing_style":    file_cfg.typing_style,
        "exclude":         list(file_cfg.exclude),
        "output_dir":      file_cfg.output_dir,
        "execution_mode":  file_cfg.execution_mode,
        "respect_all":     file_cfg.respect_all,
    }
    if args.include_private:
        cfg_kwargs["include_private"] = True
    if args.verbose:
        cfg_kwargs["verbose"] = True
    if args.strict:
        cfg_kwargs["strict"] = True
    if args.execution_mode:
        _mode_map = {
            "runtime":  ExecutionMode.RUNTIME,
            "ast_only": ExecutionMode.AST_ONLY,
            "auto":     ExecutionMode.AUTO,
        }
        cfg_kwargs["execution_mode"] = _mode_map[args.execution_mode]
    if args.typing_style:
        cfg_kwargs["typing_style"] = args.typing_style

    cfg = StubConfig(**cfg_kwargs)

    # --- Dispatch: directory vs single file --------------------------------
    if target.is_dir():
        return _run_package(target, args, cfg)
    else:
        return _run_file(target, args, cfg)


# ---------------------------------------------------------------------------
# Single-file mode
# ---------------------------------------------------------------------------

def _run_file(target: Path, args: argparse.Namespace, cfg: StubConfig) -> int:
    """Process a single .py file."""
    stub_ctx = StubContext(config=cfg)

    try:
        content = generate_stub(str(target), args.output, ctx=stub_ctx)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error generating stub: {exc}", file=sys.stderr)
        return 1

    out_path = args.output or str(target.with_suffix(".pyi"))
    print(f"Stub written to: {out_path}")

    _print_diagnostics(stub_ctx, cfg)

    if cfg.strict and stub_ctx.diagnostics.has_errors():
        _print_strict_error(len(stub_ctx.diagnostics.errors))
        return 1

    if args.print:
        print("\n--- Generated stub ---\n")
        print(content)

    return 0


# ---------------------------------------------------------------------------
# Package (directory) mode
# ---------------------------------------------------------------------------

def _run_package(target: Path, args: argparse.Namespace, cfg: StubConfig) -> int:
    """Process all .py files in a package directory recursively."""
    output_dir = args.output or cfg.output_dir

    print(f"Processing package: {target}")
    if output_dir:
        print(f"Output directory:  {output_dir}")
    else:
        print("Output: alongside source files")

    all_diagnostics: list = []

    def ctx_factory() -> StubContext:
        return StubContext(config=cfg)

    try:
        result = generate_package(
            str(target),
            output_dir=output_dir,
            ctx_factory=ctx_factory,
            config=cfg,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error processing package: {exc}", file=sys.stderr)
        return 1

    print(f"\n{result.summary()}")

    if result.failed:
        print("\nFailed files:", file=sys.stderr)
        for path, diags in result.failed:
            print(f"  {path}", file=sys.stderr)
            for d in diags:
                print(f"    {d}", file=sys.stderr)

    if cfg.verbose and all_diagnostics:
        print("\n--- Diagnostics ---", file=sys.stderr)
        for d in all_diagnostics:
            print(f"  {d}", file=sys.stderr)

    if cfg.strict and result.failed:
        print(
            f"\nPackage processing completed with {len(result.failed)} failed "
            "file(s).  Exiting 1 (--strict).",
            file=sys.stderr,
        )
        return 1

    return 0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _print_diagnostics(ctx: StubContext, cfg: StubConfig) -> None:
    if cfg.verbose and ctx.diagnostics:
        print("\n--- Diagnostics ---", file=sys.stderr)
        for d in ctx.diagnostics:
            print(f"  {d}", file=sys.stderr)
        print(f"  Summary: {ctx.diagnostics.summary()}", file=sys.stderr)


def _print_strict_error(n_errors: int) -> None:
    print(
        f"\nStub generation completed with {n_errors} error(s). "
        "Exiting 1 (--strict).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    sys.exit(main())
