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

Flags
-----
``--include-private``
    Include symbols whose names start with ``_``.  By default private
    names are excluded from the generated stub.

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
from .context import StubConfig, StubContext
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
            "after stub generation."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit with code 1 if any ERROR-level diagnostic was recorded "
            "during the run, even when the stub file was written successfully."
        ),
    )

    args = parser.parse_args(argv)

    cfg = StubConfig(
        include_private=args.include_private,
        verbose=args.verbose,
        strict=args.strict,
    )
    stub_ctx = StubContext(config=cfg)

    try:
        content = generate_stub(args.file, args.output, ctx=stub_ctx)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error generating stub: {exc}", file=sys.stderr)
        return 1

    out_path = args.output or str(Path(args.file).with_suffix(".pyi"))
    print(f"Stub written to: {out_path}")

    if args.verbose and stub_ctx.diagnostics:
        print("\n--- Diagnostics ---", file=sys.stderr)
        for d in stub_ctx.diagnostics:
            print(f"  {d}", file=sys.stderr)
        print(f"  Summary: {stub_ctx.diagnostics.summary()}", file=sys.stderr)

    if args.strict and stub_ctx.diagnostics.has_errors():
        print(
            f"\nStub generation completed with {len(stub_ctx.diagnostics.errors)} error(s). "
            "Exiting 1 (--strict).",
            file=sys.stderr,
        )
        return 1

    if args.print:
        print("\n--- Generated stub ---\n")
        print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
