"""Rendering a document over time and encoding the frames."""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypeAlias

from .._internal._registry import Registry
from .._internal._typing import AnyPath
from ._ffmpeg import encode, find_ffmpeg
from .frames import Frame, FrameData, frame_times, to_frame

if TYPE_CHECKING:
    from ..document import Document

__all__ = [
    "DEFAULT_FPS",
    "RENDERERS",
    "Renderer",
    "Update",
    "animation_duration",
    "iter_frames",
    "register_renderer",
    "render_animation",
    "resolve_renderer",
]

Renderer: TypeAlias = "Callable[[Document, float], FrameData]"
"""``renderer(document, seconds)`` returning PNG bytes or an RGBA array."""

Update: TypeAlias = "Callable[[Document, float], object]"
"""``update(document, seconds)`` changing the document before each frame."""

DEFAULT_FPS: Final = 30.0
_CLOCK_RE: Final = re.compile(r"^\s*([+-]?\d*\.?\d+)\s*(ms|s|min|h)?\s*$")
_CLOCK_SCALE: Final = {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0, None: 1.0}

RENDERERS: Final[Registry[Callable[[Document, float], FrameData]]] = Registry("renderer")


def _skia(document: Document, time: float) -> FrameData:
    from ..ops.render import skia_renderer

    return skia_renderer(document, time)


RENDERERS.add("skia", _skia)


def register_renderer(name: str) -> Callable[[Renderer], Renderer]:
    """Decorator registering a renderer so it can be chosen by *name*.

    A rasterizer package can register itself on import::

        @register_renderer("myraster")
        def render(document, seconds):
            return rasterize(document.to_string())
    """
    return RENDERERS.register(name)  # type: ignore[return-value]


def resolve_renderer(renderer: Renderer | str | None) -> Renderer:
    """A renderer from a callable, a registered name or ``"module:function"``."""
    if callable(renderer):
        return renderer
    if renderer is None:
        names = ", ".join(RENDERERS.names())
        raise ValueError(
            "no renderer given; pass renderer=callable(document, seconds) returning PNG bytes or an RGBA array, "
            f"a registered name ({names}) or 'module:function'"
        )
    if renderer in RENDERERS:
        return RENDERERS.get(renderer)
    module_name, sep, attribute = renderer.partition(":")
    if not sep:
        raise ValueError(f"unknown renderer {renderer!r}; registered: {', '.join(RENDERERS.names())}")
    found = getattr(importlib.import_module(module_name), attribute)
    if not callable(found):
        raise TypeError(f"{renderer!r} is not callable")
    return found  # type: ignore[no-any-return]


def _seconds(value: object) -> float | None:
    match = _CLOCK_RE.match(str(value))
    if match is None:
        return None
    return float(match.group(1)) * _CLOCK_SCALE[match.group(2)]


def animation_duration(document: Document) -> float | None:
    """End of the last SMIL animation (``begin + dur``) in seconds.

    Only plain clock values count; ``None`` when nothing qualifies.
    """
    from ..elements.animation import AnimationElement

    ends = []
    for element in document.root.find_all(AnimationElement):
        dur = _seconds(element.get("dur", ""))
        if dur is not None:
            ends.append((_seconds(element.get("begin", 0)) or 0.0) + dur)
    return max(ends) if ends else None


def iter_frames(
    document: Document,
    fps: float = DEFAULT_FPS,
    duration: float | None = None,
    renderer: Renderer | str | None = None,
    *,
    update: Update | None = None,
) -> Iterator[Frame]:
    """Render one frame per ``1/fps`` seconds without encoding them."""
    draw = resolve_renderer(renderer)
    length = duration if duration is not None else animation_duration(document)
    if length is None:
        raise ValueError("pass duration=...; the document has no SMIL animation with a plain 'dur'")
    for index, time in enumerate(frame_times(fps, length)):
        if update is not None:
            update(document, time)
        yield to_frame(index, time, draw(document, time))


def render_animation(
    document: Document,
    path: AnyPath,
    fps: float = DEFAULT_FPS,
    duration: float | None = None,
    renderer: Renderer | str | None = None,
    *,
    update: Update | None = None,
    ffmpeg: str | None = None,
) -> Path:
    """Render frames and encode them with ffmpeg.

    Parameters
    ----------
    document : Document
        The drawing.
    path : str or path-like
        Output file; the extension picks the encoder (``.mp4``, ``.gif``,
        ``.webm``, ``.mov``, ``.apng``, anything else ffmpeg knows).
    fps : float
        Frames per second.
    duration : float, optional
        Seconds to render; defaults to the end of the document's SMIL
        animations.
    renderer : callable, str
        ``renderer(document, seconds)`` returning PNG bytes or an
        ``(height, width, 4)`` uint8 array; a registered name such as
        ``"skia"``; or ``"module:function"``. There is no default.
    update : callable, optional
        ``update(document, seconds)`` called before each frame, for
        procedural animation.
    ffmpeg : str, optional
        The ffmpeg executable; found on ``PATH`` by default.

    Returns
    -------
    pathlib.Path
        The written file.

    Raises
    ------
    FFmpegNotFoundError
        Before rendering anything, when ffmpeg is missing.
    FFmpegError
        When ffmpeg fails.
    """
    executable = find_ffmpeg(ffmpeg)
    frames = iter_frames(document, fps, duration, renderer, update=update)
    encode(frames, path, fps, executable=executable)
    return Path(path)
