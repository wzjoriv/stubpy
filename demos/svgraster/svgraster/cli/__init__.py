"""Command line: ``python -m svgraster {render,animate,bench,fonts,backends,conformance}``.

``python -m svgraster input.svg -o output.png`` (no subcommand) still renders.
"""
from __future__ import annotations

import argparse
import sys

from .. import __version__
from . import _animate, _bench, _conformance, _fonts, _render

COMMANDS = {
    "render": _render,
    "animate": _animate,
    "bench": _bench,
    "fonts": _fonts,
    "backends": _fonts,
    "conformance": _conformance,
}
EXIT_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    """The argument parser with every subcommand."""
    parser = argparse.ArgumentParser(prog="svgraster", description="Render SVG 1.1 files to images and video.")
    parser.add_argument("--version", action="version", version=f"svgraster {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    _render.add_parser(sub)
    _animate.add_parser(sub)
    _bench.add_parser(sub)
    _fonts.add_parsers(sub)
    _conformance.add_parser(sub)
    return parser


def _legacy(argv: list[str]) -> list[str]:
    """Map the flat 0.1 form (``svgraster in.svg -o out.png``, ``--backends``) onto subcommands."""
    if "--backends" in argv:
        return ["backends"]
    if argv and argv[0] not in COMMANDS and argv[0] not in ("-h", "--help", "--version"):
        return ["render", *argv]
    return argv


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    argv = _legacy(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        parser.exit(2)
    try:
        return args.run(args, parser)
    except KeyboardInterrupt:
        print("svgraster: interrupted", file=sys.stderr)
        return EXIT_ERROR


__all__ = ["build_parser", "main"]
