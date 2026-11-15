"""``svgraster render``: one SVG to PNG, PPM or ``.npy``."""
from __future__ import annotations

import sys
from pathlib import Path

from ..fonts import FontDatabase, default_database
from ..io import FORMATS, save
from ..render import Renderer

EXIT_ERROR = 1


def add_common_options(p) -> None:
    """Size, quality and font options shared by ``render`` and ``animate``."""
    p.add_argument("--width", type=int, help="output width in pixels")
    p.add_argument("--height", type=int, help="output height in pixels")
    p.add_argument("--dpi", type=float, default=96.0, help="resolution for absolute units (default 96)")
    p.add_argument("--background", help="background color, e.g. white or #fff")
    p.add_argument("--antialias", type=int, default=16, help="sub-scanlines per pixel row (default 16)")
    p.add_argument("--supersample", type=int, default=1, help="render at N times the size and downscale")
    p.add_argument("--threads", type=int, help="OpenMP threads for the native layers")
    p.add_argument("--pure", action="store_true", help="use the numpy fallbacks only")
    p.add_argument("--font-dir", action="append", default=[], metavar="PATH",
                   help="extra font file or folder (repeatable)")


def make_renderer(args) -> Renderer:
    """A :class:`Renderer` from parsed common options."""
    fonts = None
    if args.font_dir:
        fonts = FontDatabase(args.font_dir, parent=default_database())
    return Renderer(antialias=args.antialias, supersample=args.supersample, threads=args.threads,
                    native=not args.pure, fonts=fonts)


def add_parser(sub) -> None:
    """Register ``render``."""
    p = sub.add_parser("render", help="render an SVG file to PNG, PPM or .npy",
                       description="Render an SVG file. Without a subcommand, svgraster renders too.")
    p.add_argument("input", help="SVG or SVGZ file to render")
    p.add_argument("-o", "--output", help=f"output file ({', '.join(FORMATS)}); defaults to INPUT.png")
    p.add_argument("--time", type=float, help="evaluate SMIL animations at this many seconds")
    p.add_argument("--float", action="store_true", help="store float32 instead of uint8 (.npy only)")
    add_common_options(p)
    p.set_defaults(run=run)


def run(args, parser) -> int:
    """Render one file."""
    output = Path(args.output) if args.output else Path(args.input).with_suffix(".png")
    if output.suffix.lower() not in FORMATS:
        parser.error(f"unsupported output format {output.suffix!r} (use {', '.join(FORMATS)})")
    try:
        renderer = make_renderer(args)
        dtype = "float32" if args.float and output.suffix.lower() == ".npy" else "uint8"
        image = renderer.render(args.input, width=args.width, height=args.height, dpi=args.dpi,
                                background=args.background, dtype=dtype, time=args.time)
        save(image, output)
    except (OSError, ValueError, TypeError) as exc:
        print(f"svgraster: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"wrote {output} ({image.shape[1]}x{image.shape[0]})")
    return 0
