"""Turning documents into video and GIF files through ffmpeg.

svgwriter does not rasterize by itself. A *renderer* is any callable
``renderer(document, seconds)`` returning PNG bytes or an
``(height, width, 4)`` uint8 RGBA array; frames are piped to ``ffmpeg``.
With skia-python installed the ``"skia"`` renderer is available.

Example
-------
>>> import svgwriter as svg
>>> doc = svg.Document(64, 64)
>>> dot = doc.circle(32, 32, 4, fill="tomato")
>>> def grow(document, t):
...     dot.r = 4 + 20 * t
>>> doc.render_animation("grow.gif", fps=12, duration=1, renderer="skia", update=grow)  # doctest: +SKIP
"""

from __future__ import annotations

from ._ffmpeg import FFmpegError, FFmpegNotFoundError, find_ffmpeg
from .animation import (
    DEFAULT_FPS,
    RENDERERS,
    Renderer,
    Update,
    animation_duration,
    iter_frames,
    register_renderer,
    render_animation,
    resolve_renderer,
)
from .frames import Frame, FrameData, RGBAArray, frame_times

__all__ = [
    "DEFAULT_FPS",
    "RENDERERS",
    "FFmpegError",
    "FFmpegNotFoundError",
    "Frame",
    "FrameData",
    "RGBAArray",
    "Renderer",
    "Update",
    "animation_duration",
    "find_ffmpeg",
    "frame_times",
    "iter_frames",
    "register_renderer",
    "render_animation",
    "resolve_renderer",
]
