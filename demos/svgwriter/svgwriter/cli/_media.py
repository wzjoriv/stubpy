"""``animate``, ``render`` and ``outline``: commands needing ffmpeg or skia."""

from __future__ import annotations

import argparse
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from ..document import Document
from ..ops import MissingDependencyError
from ..video import FFmpegError, FFmpegNotFoundError
from ..video.animation import DEFAULT_FPS, RENDERERS
from ._basic import emit, output_options

__all__ = ["SceneError", "add_media_commands", "load_scene"]

SCENE_FACTORIES: Final = ("build", "scene")
SCENE_DOCUMENTS: Final = ("document", "doc")
EXIT_FAILURE: Final = 1
DEFAULT_TEXT_SIZE: Final = 48.0
DEFAULT_FONT: Final = "sans-serif"
TEXT_MARGIN: Final = 4.0


class SceneError(ValueError):
    """A scene script does not define a document."""


def load_scene(path: str | Path) -> tuple[Document, Callable[[Document, float], object] | None, dict[str, Any]]:
    """Load ``(document, update, settings)`` from an ``.svg`` or ``.py`` file.

    A Python scene defines ``build()`` (or ``scene()``) returning a
    :class:`~svgwriter.Document`, or a module-level ``document``. It may
    define ``update(document, seconds)`` and the settings ``FPS``,
    ``DURATION`` and ``RENDERER``.
    """
    source = Path(path)
    if source.suffix.lower() == ".svg":
        return Document.from_file(source), None, {}
    namespace = runpy.run_path(str(source), run_name="__scene__")
    document = None
    for name in SCENE_FACTORIES:
        if callable(namespace.get(name)):
            document = namespace[name]()
            break
    else:
        document = next((namespace[n] for n in SCENE_DOCUMENTS if n in namespace), None)
    if not isinstance(document, Document):
        raise SceneError(f"{source} must define build() returning a svgwriter.Document, or a 'document' variable")
    settings = {key.lower(): namespace[key] for key in ("FPS", "DURATION", "RENDERER") if key in namespace}
    update = namespace.get("update")
    return document, update if callable(update) else None, settings


def _fail(message: str) -> int:
    print(f"svgwriter: error: {message}", file=sys.stderr)
    return EXIT_FAILURE


def _cmd_animate(args: argparse.Namespace) -> int:
    try:
        document, update, settings = load_scene(args.scene)
        written = document.render_animation(
            args.output,
            fps=args.fps if args.fps is not None else settings.get("fps", DEFAULT_FPS),
            duration=args.duration if args.duration is not None else settings.get("duration"),
            renderer=args.renderer or settings.get("renderer"),
            update=update,
            ffmpeg=args.ffmpeg,
        )
    except (SceneError, FFmpegNotFoundError, FFmpegError, MissingDependencyError, ValueError) as exc:
        return _fail(str(exc))
    print(written)
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    from ..ops.render import rasterize

    try:
        document, update, _ = load_scene(args.scene)
        if update is not None:
            update(document, args.time)
        data = rasterize(document, scale=args.scale, background=args.background)
    except (SceneError, MissingDependencyError) as exc:
        return _fail(str(exc))
    Path(args.output).write_bytes(data)
    print(args.output)
    return 0


def _cmd_outline(args: argparse.Namespace) -> int:
    from ..ops.text import text_to_path

    try:
        path = text_to_path(args.text, args.font, args.size, fill=args.fill)
    except MissingDependencyError as exc:
        return _fail(str(exc))
    box = path.bbox
    document = Document(box.width + 2 * TEXT_MARGIN, box.height + 2 * TEXT_MARGIN)
    document += path * f"translate({TEXT_MARGIN - box.x:g} {TEXT_MARGIN - box.y:g})"
    emit(document.root, args)
    return 0


def add_media_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    animate = commands.add_parser(
        "animate",
        help="render a scene to mp4/gif/webm through ffmpeg",
        description="Render a scene (.py defining build() and optionally update(doc, t), or an .svg) "
        "frame by frame and encode it with ffmpeg.",
    )
    animate.add_argument("scene", help="scene script (.py) or SVG file")
    animate.add_argument("-o", "--out", "--output", dest="output", default="animation.mp4", help="output file; the extension picks the format")
    animate.add_argument("--fps", type=float, default=None, help=f"frames per second (default: scene FPS or {DEFAULT_FPS:g})")
    animate.add_argument("--duration", type=float, default=None, help="seconds (default: scene DURATION or the SMIL animation length)")
    animate.add_argument("--renderer", default=None, help=f"registered name ({', '.join(RENDERERS.names())}) or module:function")
    animate.add_argument("--ffmpeg", default=None, help="ffmpeg executable (default: found on PATH)")
    animate.set_defaults(func=_cmd_animate)

    render = commands.add_parser("render", help="rasterize a scene or SVG file to PNG (needs skia-python)")
    render.add_argument("scene", help="scene script (.py) or SVG file")
    render.add_argument("-o", "--out", "--output", dest="output", default="out.png")
    render.add_argument("--time", type=float, default=0.0, help="seconds passed to the scene's update()")
    render.add_argument("--scale", type=float, default=1.0, help="pixels per user unit")
    render.add_argument("--background", default=None, help="background color (default: transparent)")
    render.set_defaults(func=_cmd_render)

    outline = commands.add_parser("outline", help="write text as glyph outlines (needs skia-python)")
    outline.add_argument("text")
    outline.add_argument("--font", default=DEFAULT_FONT)
    outline.add_argument("--size", type=float, default=DEFAULT_TEXT_SIZE)
    outline.add_argument("--fill", default="black")
    output_options(outline)
    outline.set_defaults(func=_cmd_outline)
