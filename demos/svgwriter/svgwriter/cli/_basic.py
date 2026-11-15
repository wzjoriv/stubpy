"""``shapes``, ``elements``, ``draw``, ``format`` and ``info``."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from typing import Final

from ..builder import SHAPES
from ..document import Document
from ..elements.base import Category, Element
from ..io.parser import Strictness, parse_file
from ..io.writer import SerializeOptions

__all__ = ["add_basic_commands", "emit", "output_options"]

DEFAULT_CANVAS: Final = 200.0
CANVAS_MARGIN: Final = 0.4
STROKE_WIDTH: Final = 2


def _cmd_shapes(args: argparse.Namespace) -> int:
    for name in SHAPES.names():
        print(name)
    return 0


def _cmd_elements(args: argparse.Namespace) -> int:
    for category in Category:
        tags = sorted(Element.registered(category))
        if tags:
            print(f"{category.name.lower()}: {' '.join(tags)}")
    return 0


def _cmd_draw(args: argparse.Namespace) -> int:
    size = args.size
    doc = Document(size, size)
    center, radius = size / 2, size * CANVAS_MARGIN
    factory = SHAPES.get(args.shape)
    if args.shape == "arrow":
        shape = factory(center - radius, center, center + radius, center, stroke=args.fill, stroke_width=STROKE_WIDTH)
    else:
        shape = factory(center, center, radius, fill=args.fill, stroke=args.stroke)
    doc += shape
    emit(doc.root, args)
    return 0


def _cmd_format(args: argparse.Namespace) -> int:
    emit(parse_file(args.input, strictness=Strictness.WARN), args)
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    counts = Counter(element.tag for element in parse_file(args.input).iter())
    for tag, count in counts.most_common():
        print(f"{count:6d}  {tag}")
    return 0


def emit(root: Element, args: argparse.Namespace) -> None:
    """Write *root* to ``--output`` or stdout using the output options."""
    options = SerializeOptions(pretty=not args.compact, precision=args.precision, compact_paths=args.compact)
    if args.output:
        root.save(args.output, options=options)
    else:
        sys.stdout.write(root.to_string(options=options))


def output_options(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("-o", "--output", help="write here instead of stdout")
    sub.add_argument("--compact", action="store_true", help="single-line output, shortest path data")
    sub.add_argument("--precision", type=int, default=SerializeOptions().precision)


def add_basic_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    commands.add_parser("shapes", help="list registered composite shapes").set_defaults(func=_cmd_shapes)
    commands.add_parser("elements", help="list supported elements by category").set_defaults(func=_cmd_elements)

    draw = commands.add_parser("draw", help="render a registered shape")
    draw.add_argument("shape", choices=SHAPES.names())
    draw.add_argument("--size", type=float, default=DEFAULT_CANVAS)
    draw.add_argument("--fill", default="steelblue")
    draw.add_argument("--stroke", default=None)
    output_options(draw)
    draw.set_defaults(func=_cmd_draw)

    fmt = commands.add_parser("format", help="parse a file and write it back out")
    fmt.add_argument("input")
    output_options(fmt)
    fmt.set_defaults(func=_cmd_format)

    info = commands.add_parser("info", help="count elements in a file")
    info.add_argument("input")
    info.set_defaults(func=_cmd_info)
