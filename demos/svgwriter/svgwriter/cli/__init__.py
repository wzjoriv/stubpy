"""The ``python -m svgwriter`` command line.

Commands
--------
shapes, elements    list registered composite shapes and element classes
draw                write a registered shape
format, info        re-serialize or summarize an SVG file
animate             render a scene to mp4/gif/webm through ffmpeg
render              rasterize a scene or SVG file to PNG (skia-python)
outline             write text as glyph outlines (skia-python)
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .. import __version__
from ._basic import add_basic_commands
from ._media import SceneError, add_media_commands, load_scene

__all__ = ["SceneError", "build_parser", "load_scene", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="svgwriter", description="Write, reformat, inspect and animate SVG 1.1 files.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    add_basic_commands(commands)
    add_media_commands(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
