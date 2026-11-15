"""Frame data returned by renderers: PNG bytes or RGBA arrays."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Final, Protocol, TypeAlias, runtime_checkable

__all__ = ["Frame", "FrameData", "RGBAArray", "frame_times", "to_frame"]

PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
PNG_SIZE_OFFSET: Final = 16
RGBA_CHANNELS: Final = 4
RGBA_DTYPE: Final = "uint8"


@runtime_checkable
class RGBAArray(Protocol):
    """An array of shape ``(height, width, 4)`` and dtype ``uint8``.

    NumPy arrays qualify, as does anything with ``shape`` and ``tobytes``.
    """

    @property
    def shape(self) -> tuple[int, ...]: ...

    def tobytes(self) -> bytes: ...


FrameData: TypeAlias = bytes | bytearray | memoryview | RGBAArray
"""What a renderer returns for one frame."""


@dataclass(frozen=True, slots=True)
class Frame:
    """One rendered frame, ready for the encoder."""

    index: int
    time: float
    width: int
    height: int
    data: bytes
    png: bool


def _png_size(data: bytes) -> tuple[int, int]:
    width, height = struct.unpack(">II", data[PNG_SIZE_OFFSET:PNG_SIZE_OFFSET + 8])
    return width, height


def to_frame(index: int, time: float, data: FrameData) -> Frame:
    """Check and wrap renderer output."""
    if isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
        if not raw.startswith(PNG_SIGNATURE):
            raise TypeError("renderer returned bytes that are not a PNG; return PNG bytes or an RGBA array")
        width, height = _png_size(raw)
        return Frame(index, time, width, height, raw, True)
    if isinstance(data, RGBAArray):
        shape = tuple(data.shape)
        if len(shape) != 3 or shape[2] != RGBA_CHANNELS:
            raise ValueError(f"RGBA frames need shape (height, width, 4), got {shape}")
        dtype = getattr(data, "dtype", RGBA_DTYPE)
        if str(dtype) != RGBA_DTYPE:
            raise ValueError(f"RGBA frames need dtype uint8, got {dtype}")
        return Frame(index, time, int(shape[1]), int(shape[0]), data.tobytes(), False)
    raise TypeError(f"renderer returned {type(data).__name__}; expected PNG bytes or an RGBA array")


def frame_times(fps: float, duration: float) -> list[float]:
    """Sample times ``0, 1/fps, ...`` covering *duration* seconds."""
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    count = max(1, math.ceil(round(fps * duration, 9)))
    return [index / fps for index in range(count)]
