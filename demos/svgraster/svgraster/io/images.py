"""Decoding raster images (PNG, baseline JPEG) into premultiplied float32 RGBA."""
from __future__ import annotations

import numpy as np

from .jpeg import JpegError, decode_jpeg
from .png import decode_png_rgba
from .resources import sniff

RASTER_TYPES = ("image/png", "image/jpeg")


def decode_image(data: bytes, media_type: str | None = None) -> np.ndarray:
    """Decode PNG or JPEG bytes into an ``(H, W, 4)`` uint8 straight-alpha array."""
    kind = sniff(data) if media_type not in RASTER_TYPES else media_type
    if data.startswith(b"\x89PNG"):
        kind = "image/png"
    elif data.startswith(b"\xff\xd8"):
        kind = "image/jpeg"
    if kind == "image/png":
        return decode_png_rgba(data)
    if kind == "image/jpeg":
        return decode_jpeg(data)
    raise ValueError(f"unsupported image type {media_type or kind!r}")


def premultiplied(rgba8: np.ndarray) -> np.ndarray:
    """uint8 straight alpha to premultiplied float32 (numba when available)."""
    from .. import _jit

    return _jit.premultiply_u8(rgba8)


__all__ = ["JpegError", "decode_image", "premultiplied"]
