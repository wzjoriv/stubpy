"""
stubpy.__main__
===============

CLI entry point — invoked via ``python -m stubpy`` or the ``stubpy``
console script installed by ``pip install stubpy``.

Usage::

    stubpy path/to/module.py
    stubpy path/to/module.py -o path/to/module.pyi
    stubpy path/to/module.py --print
    stubpy path/to/module.py --verbose
    stubpy path/to/module.py --strict

Flags
-----
``--verbose``
    Print all INFO, WARNING, and ERROR diagnostics to stderr after
    generation completes.

``--strict``
    Exit with code 1 if any ERROR-level diagnostic was recorded during
    the run, even if the stub file was written successfully.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import generate_stub
from .diagnostics import DiagnosticCollector, DiagnosticStage


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``stubpy`` command-line interface.

    Parameters
    ----------
    argv : list of str, optional
        Argument list to parse. Defaults to ``None``, in which case
        :mod:`argparse` reads from :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` on success, ``1`` on any error or (with ``--strict``) any
        ERROR-level diagnostic.
    """
    parser = argparse.ArgumentParser(
        prog="stubpy",
        description=(
            "Generate a .pyi stub file for a Python source module, with "
            "full **kwargs and *args backtracing through the class MRO."
        ),
    )
    parser.add_argument(
        "file",
        help="Python source file to stub",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="PATH",
        help="Output .pyi path (default: same stem and directory as input)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the generated stub to stdout after writing the file",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        help=(
            "Include symbols whose names start with '_'. "
            "By default, private names are excluded from the stub."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Print all diagnostics (INFO, WARNING, ERROR) to stderr "
            "after stub generation. Without this flag only errors are "
            "shown on failure."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit with code 1 if any ERROR-level diagnostic was recorded "
            "during the run, even when the stub file was written "
            "successfully."
        ),
    )

    args = parser.parse_args(argv)

    try:
        from .context import StubConfig
        cfg = StubConfig(
            include_private=args.include_private,
            verbose=args.verbose,
            strict=args.strict,
        )
        from .context import StubContext as _StubContext
        stub_ctx = _StubContext(config=cfg)
        content = generate_stub(args.file, args.output, ctx=stub_ctx)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error generating stub: {exc}", file=sys.stderr)
        return 1

    out_path = args.output or str(Path(args.file).with_suffix(".pyi"))
    print(f"Stub written to: {out_path}")

    if args.verbose or args.strict:
        result = _report_diagnostics(
            args.file, verbose=args.verbose, strict=args.strict
        )
        if result != 0:
            return result

    if args.print:
        print("\n--- Generated stub ---\n")
        print(content)

    return 0


def _report_diagnostics(
    filepath: str,
    verbose: bool,
    strict: bool,
) -> int:
    """Run the load and AST-harvest stages to collect diagnostics, then
    print and/or enforce them according to *verbose* and *strict*.

    Parameters
    ----------
    filepath : str
        Path to the source file that was stubbed.
    verbose : bool
        When ``True``, print all diagnostics to ``stderr``.
    strict : bool
        When ``True``, return ``1`` if any ERROR was recorded.

    Returns
    -------
    int
        ``1`` if *strict* and errors were found, else ``0``.
    """
    from .loader import load_module
    from .ast_pass import ast_harvest
    from .symbols import build_symbol_table

    diag = DiagnosticCollector()

    try:
        mod, path, mod_name = load_module(filepath, diagnostics=diag)
        source = path.read_text(encoding="utf-8")
        ast_symbols = ast_harvest(source)
        if ast_symbols.all_exports is not None:
            diag.info(
                DiagnosticStage.AST_PASS,
                path.name,
                f"__all__ found: {ast_symbols.all_exports}",
            )
        tbl = build_symbol_table(mod, mod_name, ast_symbols)
        diag.info(
            DiagnosticStage.SYMBOL_TABLE,
            path.name,
            f"Symbol table: {len(tbl)} symbols",
        )
    except Exception as exc:
        diag.error(DiagnosticStage.LOAD, filepath, str(exc))

    if verbose and diag:
        print("\n--- Diagnostics ---", file=sys.stderr)
        for d in diag:
            print(f"  {d}", file=sys.stderr)
        print(f"  Summary: {diag.summary()}", file=sys.stderr)

    if strict and diag.has_errors():
        print(
            f"\nStub generation completed with {len(diag.errors)} error(s). "
            "Exiting 1 (--strict).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
