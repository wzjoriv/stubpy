"""Frame sequences and video output: PNG sequences, ``.npy`` stacks, or ffmpeg over a pipe."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

from .. import _backend
from ..dom.document import Document
from ..io import save
from ._snapshot import timeline

FFMPEG_ENV = "SVGRASTER_FFMPEG"
DEFAULT_FPS = 30.0
DEFAULT_DURATION = 1.0
MAX_FRAMES = 100_000
EVEN_PAD = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
GIF_FILTER = "split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse"
VIDEO_ARGS = {
    ".mp4": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", EVEN_PAD, "-crf", "18", "-movflags", "+faststart"],
    ".mov": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", EVEN_PAD, "-crf", "18"],
    ".mkv": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", EVEN_PAD, "-crf", "18"],
    ".webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30"],
    ".gif": ["-filter_complex", GIF_FILTER],
    ".apng": ["-plays", "0", "-f", "apng"],
}
OPAQUE_FORMATS = frozenset({".mp4", ".mov", ".mkv"})


class FFmpegNotFoundError(RuntimeError):
    """ffmpeg is needed for video output but was not found."""


def find_ffmpeg(executable: str | os.PathLike | None = None) -> str:
    """The ffmpeg executable: ``executable``, ``SVGRASTER_FFMPEG``, or ``ffmpeg`` on ``PATH``."""
    candidate = os.fspath(executable) if executable else os.environ.get(FFMPEG_ENV, "ffmpeg")
    found = shutil.which(candidate)
    if found is None:
        raise FFmpegNotFoundError(
            f"ffmpeg was not found ({candidate!r}). Install ffmpeg and put it on PATH, set {FFMPEG_ENV}, "
            "or write a PNG sequence instead, e.g. 'frames/frame_%04d.png'.")
    return found


def frame_times(duration: float, fps: float, start: float = 0.0) -> list[float]:
    """The sample times of a clip of ``duration`` seconds at ``fps``."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    if duration < 0:
        raise ValueError("duration must not be negative")
    count = max(1, int(round(duration * fps)))
    if count > MAX_FRAMES:
        raise ValueError(f"{count} frames requested; the limit is {MAX_FRAMES}")
    return [start + i / fps for i in range(count)]


def _renderer(options: dict):
    from ..render import Renderer

    keys = ("antialias", "supersample", "threads", "tolerance", "native", "fonts")
    return Renderer(**{k: options.pop(k) for k in keys if k in options})


def frame_renderer(svg, **options) -> Callable[[float], np.ndarray]:
    """A callable ``f(t)`` returning the RGBA frame at ``t`` seconds; the document is parsed once.

    ``**options`` mix :class:`~svgraster.Renderer` settings and :meth:`~svgraster.Renderer.render`
    keywords such as ``width``, ``background`` and ``dtype``.
    """
    doc = Document.parse(svg, base_dir=options.pop("base_dir", None))
    renderer = _renderer(options)

    def render_at(t: float) -> np.ndarray:
        return renderer.render_document(doc, time=float(t), **options)

    render_at.document = doc
    render_at.renderer = renderer
    return render_at


def frames(svg, *, fps: float = DEFAULT_FPS, duration: float | None = None, start: float = 0.0,
           **options) -> Iterator[tuple[float, np.ndarray]]:
    """Yield ``(time, image)`` for each frame; ``duration`` defaults to the document's timeline."""
    render_at = frame_renderer(svg, **options)
    if duration is None:
        duration = timeline(render_at.document) or DEFAULT_DURATION
    for t in frame_times(duration, fps, start):
        yield t, render_at(t)


def _pack(image: np.ndarray, packer) -> bytes:
    if packer is not None:
        return packer.pack(image)
    from ..raster import composite

    return composite.to_uint8(image, unpremultiply=True).tobytes()


def render_animation(svg, output: str | os.PathLike, *, fps: float = DEFAULT_FPS, duration: float | None = None,
                     start: float = 0.0, ffmpeg: str | os.PathLike | None = None,
                     extra_args: list[str] | None = None, **options) -> Path:
    """Render an animated document to a video, GIF, ``.npy`` stack or PNG sequence (``name_%04d.png``).

    Video formats are encoded by piping raw RGBA frames to ffmpeg; PNG sequences and ``.npy`` need
    no external program. Returns the output path.
    """
    out = Path(output)
    suffix = out.suffix.lower()
    if "%" in out.name:
        out.parent.mkdir(parents=True, exist_ok=True)
        for i, (_, image) in enumerate(frames(svg, fps=fps, duration=duration, start=start, **options)):
            save(image, str(out) % i)
        return out
    if suffix == ".npy":
        stack = np.stack([img for _, img in frames(svg, fps=fps, duration=duration, start=start, **options)])
        np.save(out, stack)
        return out
    if suffix not in VIDEO_ARGS:
        raise ValueError(f"unsupported animation output {suffix!r}; use one of {', '.join(VIDEO_ARGS)}, "
                         ".npy or a %-pattern .png sequence")
    exe = find_ffmpeg(ffmpeg)
    if suffix in OPAQUE_FORMATS and options.get("background") is None:
        options["background"] = "white"
    options["dtype"] = "float32"
    options["premultiplied"] = True
    seq = frames(svg, fps=fps, duration=duration, start=start, **options)
    _, first = next(seq)
    h, w = first.shape[:2]
    composite_mod = _backend.native("composite")
    packer = composite_mod.FramePacker(w, h) if composite_mod is not None else None
    cmd = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r",
           f"{fps:g}", "-i", "-", *VIDEO_ARGS[suffix], *(extra_args or []), str(out)]
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            proc.stdin.write(_pack(first, packer))
            for _, image in seq:
                proc.stdin.write(_pack(image, packer))
            proc.stdin.close()
        except BrokenPipeError:
            pass
        finally:
            code = proc.wait()
        if code != 0:
            log.seek(0)
            message = log.read().decode("utf-8", "replace").strip().splitlines()[-5:]
            raise RuntimeError(f"ffmpeg failed with exit code {code}: {' '.join(message)}")
    return out
