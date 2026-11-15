"""SMIL animation: timing, interpolation, motion paths, document snapshots and video output."""
from ._snapshot import ANIMATION_TAGS, Animation, collect, snapshot, timeline
from ._timing import INDEFINITE, Scheduler, Timing, parse_clock
from ._values import Value, bezier_ease, interpolate, parse_value
from .video import FFmpegNotFoundError, find_ffmpeg, frame_renderer, frame_times, frames, render_animation

__all__ = [
    "ANIMATION_TAGS",
    "INDEFINITE",
    "Animation",
    "FFmpegNotFoundError",
    "Scheduler",
    "Timing",
    "Value",
    "bezier_ease",
    "collect",
    "find_ffmpeg",
    "frame_renderer",
    "frame_times",
    "frames",
    "interpolate",
    "parse_clock",
    "parse_value",
    "render_animation",
    "snapshot",
    "timeline",
]
