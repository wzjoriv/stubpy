"""The ``python -m svgwriter.cli`` command line: one ``draw`` command."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .document import Document

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="svgwriter", description="Draw a shape as SVG.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    draw = commands.add_parser("draw", help="draw a circle or a square")
    draw.add_argument("shape", choices=["circle", "square"])
    draw.add_argument("--size", type=float, default=200.0)
    draw.add_argument("--fill", default="gold")
    draw.set_defaults(func=_draw)
    return parser


def _draw(args: argparse.Namespace) -> int:
    doc = Document(args.size, args.size)
    if args.shape == "circle":
        doc.circle(args.size / 2, args.size / 2, args.size * 0.4, fill=args.fill)
    else:
        doc.add_shape("square", size=args.size * 0.8, x=args.size * 0.1, y=args.size * 0.1, fill=args.fill)
    sys.stdout.write(doc.to_string())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
