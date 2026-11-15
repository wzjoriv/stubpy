"""``svgraster animate``: an animated SVG to MP4, WebM, GIF, ``.npy`` or a PNG sequence."""
from __future__ import annotations

import sys
from pathlib import Path

from ..animation import FFmpegNotFoundError, render_animation, timeline
from ..dom.document import Document
from ._render import EXIT_ERROR, add_common_options, make_renderer


def add_parser(sub) -> None:
    """Register ``animate``."""
    p = sub.add_parser("animate", help="render SMIL animation to video or frames",
                       description="Render an animated SVG. Video formats need ffmpeg on PATH; "
                                   "a %%-pattern such as frames/f_%%04d.png writes PNG frames without it.")
    p.add_argument("input", help="SVG file with SMIL animation")
    p.add_argument("-o", "--output", help="output (.mp4, .webm, .gif, .mov, .mkv, .apng, .npy or name_%%04d.png); "
                                          "defaults to INPUT.mp4")
    p.add_argument("--fps", type=float, default=30.0, help="frames per second (default 30)")
    p.add_argument("--duration", type=float, help="seconds to render (default: the document's timeline)")
    p.add_argument("--start", type=float, default=0.0, help="first frame time in seconds")
    p.add_argument("--ffmpeg", help="path to the ffmpeg executable")
    add_common_options(p)
    p.set_defaults(run=run)


def run(args, parser) -> int:
    """Render the animation."""
    output = Path(args.output) if args.output else Path(args.input).with_suffix(".mp4")
    try:
        renderer = make_renderer(args)
        doc = Document.parse(args.input)
        duration = args.duration if args.duration is not None else (timeline(doc) or 1.0)
        render_animation(doc, output, fps=args.fps, duration=duration, start=args.start, ffmpeg=args.ffmpeg,
                         width=args.width, height=args.height, dpi=args.dpi, background=args.background,
                         antialias=renderer.antialias, supersample=renderer.supersample, threads=renderer.threads,
                         native=renderer.native, fonts=renderer.fonts)
    except FFmpegNotFoundError as exc:
        print(f"svgraster: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(f"svgraster: {exc}", file=sys.stderr)
        return EXIT_ERROR
    frames = max(1, round(duration * args.fps))
    print(f"wrote {output} ({frames} frames, {duration:g} s at {args.fps:g} fps)")
    return 0
