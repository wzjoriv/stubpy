"""
stubpy.__main__
===============

CLI entry point — invoked via ``python -m stubpy`` or the ``stubpy``
console script installed by ``pip install stubpy``.

Usage::

    stubpy path/to/module.py
    stubpy path/to/module.py -o path/to/module.pyi
    stubpy path/to/module.py --print
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import generate_stub


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``stubpy`` command-line interface.

    Parses *argv* (or :data:`sys.argv` when ``None``), calls
    :func:`~stubpy.generator.generate_stub`, and prints a confirmation
    message.

    Parameters
    ----------
    argv : list of str, optional
        Argument list to parse. Defaults to ``None``, in which case
        :mod:`argparse` reads from :data:`sys.argv`.

    Returns
    -------
    int
        ``0`` on success, ``1`` on any error.
    """
    parser = argparse.ArgumentParser(
        prog="stubpy",
        description=(
            "Generate a .pyi stub file for a Python source module, with "
            "full **kwargs and *args backtracing through the class MRO."
        ),
    )
    parser.add_argument("file", help="Python source file to stub")
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
    args = parser.parse_args(argv)

    try:
        content = generate_stub(args.file, args.output)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error generating stub: {exc}", file=sys.stderr)
        return 1

    out_path = args.output or str(Path(args.file).with_suffix(".pyi"))
    print(f"✓ Stub written to: {out_path}")

    if args.print:
        print("\n--- Generated stub ---\n")
        print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
