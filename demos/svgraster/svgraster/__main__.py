"""Command line: ``python -m svgraster input.svg -o output.png``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, backend_info
from .io import FORMATS, save
from .render import Renderer


def build_parser() -> argparse.ArgumentParser:
    """The argument parser."""
    parser = argparse.ArgumentParser(prog="svgraster", description="Render SVG files to PNG, PPM or .npy.")
    parser.add_argument("input", nargs="?", help="SVG file to render")
    parser.add_argument("-o", "--output", help=f"output file ({', '.join(FORMATS)}); defaults to INPUT.png")
    parser.add_argument("--width", type=int, help="output width in pixels")
    parser.add_argument("--height", type=int, help="output height in pixels")
    parser.add_argument("--dpi", type=float, default=96.0, help="resolution for absolute units (default 96)")
    parser.add_argument("--background", help="background color, e.g. white or #fff")
    parser.add_argument("--antialias", type=int, default=16, help="sub-scanlines per pixel row")
    parser.add_argument("--supersample", type=int, default=1, help="render at N times the size and downscale")
    parser.add_argument("--threads", type=int, help="OpenMP threads for the native layers")
    parser.add_argument("--float", action="store_true", help="store float32 instead of uint8 (.npy only)")
    parser.add_argument("--pure", action="store_true", help="use the numpy fallbacks only")
    parser.add_argument("--backends", action="store_true", help="print the native backend report and exit")
    parser.add_argument("--version", action="version", version=f"svgraster {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.backends:
        print(json.dumps(backend_info(), indent=2))
        return 0
    if not args.input:
        parser.error("an input file is required")
    output = Path(args.output) if args.output else Path(args.input).with_suffix(".png")
    if output.suffix.lower() not in FORMATS:
        parser.error(f"unsupported output format {output.suffix!r}")
    renderer = Renderer(antialias=args.antialias, supersample=args.supersample, threads=args.threads,
                        native=not args.pure)
    dtype = "float32" if args.float and output.suffix.lower() == ".npy" else "uint8"
    try:
        image = renderer.render(args.input, width=args.width, height=args.height, dpi=args.dpi,
                                background=args.background, dtype=dtype)
    except (OSError, ValueError) as exc:
        print(f"svgraster: {exc}", file=sys.stderr)
        return 1
    save(image, output)
    print(f"wrote {output} ({image.shape[1]}x{image.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
