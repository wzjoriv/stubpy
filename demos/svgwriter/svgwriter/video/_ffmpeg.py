"""Piping frames into an ``ffmpeg`` subprocess."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from typing import Final

from .._internal._typing import AnyPath
from .frames import Frame

__all__ = ["FFmpegError", "FFmpegNotFoundError", "encode", "find_ffmpeg", "input_args", "output_args"]

FFMPEG: Final = "ffmpeg"
STDERR_TAIL: Final = 2000
EVEN_PAD: Final = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
GIF_FILTER: Final = "split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse"
_OUTPUTS: Final = {
    ".mp4": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", EVEN_PAD, "-movflags", "+faststart"],
    ".m4v": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", EVEN_PAD],
    ".mov": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", EVEN_PAD],
    ".webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p"],
    ".gif": ["-filter_complex", GIF_FILTER, "-loop", "0"],
    ".apng": ["-plays", "0", "-f", "apng"],
}


class FFmpegNotFoundError(RuntimeError):
    """``ffmpeg`` is not installed or not on ``PATH``."""


class FFmpegError(RuntimeError):
    """``ffmpeg`` ran but failed."""


def find_ffmpeg(executable: str | None = None) -> str:
    """Full path of the ffmpeg executable.

    Raises
    ------
    FFmpegNotFoundError
        When it cannot be found; nothing has been rendered at that point.
    """
    found = shutil.which(executable or FFMPEG)
    if found is None:
        raise FFmpegNotFoundError(
            f"{executable or FFMPEG!r} was not found on PATH; install ffmpeg (https://ffmpeg.org) "
            "or pass ffmpeg='/path/to/ffmpeg'. Nothing was rendered."
        )
    return found


def output_args(path: AnyPath) -> list[str]:
    """Encoder arguments chosen from the output file's extension."""
    return list(_OUTPUTS.get(os.path.splitext(os.fspath(path))[1].lower(), []))


def input_args(first: Frame, fps: float) -> list[str]:
    """Arguments describing the piped input format."""
    rate = ["-framerate", f"{fps:g}"]
    if first.png:
        return [*rate, "-f", "image2pipe", "-c:v", "png", "-i", "-"]
    size = f"{first.width}x{first.height}"
    return [*rate, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", size, "-i", "-"]


def _checked(frames: Iterator[Frame], first: Frame) -> Iterator[Frame]:
    yield first
    for frame in frames:
        if (frame.png, frame.width, frame.height) != (first.png, first.width, first.height):
            raise ValueError(
                f"frame {frame.index} is {frame.width}x{frame.height}"
                f"{' PNG' if frame.png else ' RGBA'}; frame 0 was {first.width}x{first.height}"
                f"{' PNG' if first.png else ' RGBA'}"
            )
        yield frame


def _write(process: subprocess.Popen[bytes], data: bytes) -> bool:
    """Send one frame; ``False`` once ffmpeg has stopped reading."""
    assert process.stdin is not None
    try:
        process.stdin.write(data)
    except OSError:
        return False
    return True


def encode(frames: Iterable[Frame], path: AnyPath, fps: float, *, executable: str) -> None:
    """Run ffmpeg once, writing every frame to its stdin."""
    stream = iter(frames)
    first = next(stream, None)
    if first is None:
        raise ValueError("no frames to encode")
    command = [executable, "-y", "-loglevel", "error", *input_args(first, fps), *output_args(path), os.fspath(path)]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        assert process.stdin is not None
        try:
            for frame in _checked(stream, first):
                if not _write(process, frame.data):
                    break
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            with contextlib.suppress(OSError):
                process.stdin.close()
        code = process.wait()
        if code != 0:
            errors.seek(0)
            message = errors.read().decode("utf-8", "replace")[-STDERR_TAIL:]
            raise FFmpegError(f"ffmpeg exited with status {code}: {message.strip()}")
