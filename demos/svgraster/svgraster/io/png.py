"""Minimal PNG encoding and decoding (8-bit RGBA/RGB, zlib only)."""
from __future__ import annotations

import os
import struct
import zlib

import numpy as np

SIGNATURE = b"\x89PNG\r\n\x1a\n"
BIT_DEPTH = 8
COLOR_RGB = 2
COLOR_RGBA = 6
FILTER_NONE = 0
FILTER_SUB = 1
FILTER_UP = 2
FILTER_AVERAGE = 3
FILTER_PAETH = 4
COMPRESSION_LEVEL = 6
CHANNELS = {COLOR_RGB: 3, COLOR_RGBA: 4}


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def encode_png(image: np.ndarray) -> bytes:
    """Encode an ``(H, W, 3|4)`` uint8 array as PNG bytes."""
    img = np.ascontiguousarray(image, dtype=np.uint8)
    if img.ndim != 3 or img.shape[2] not in (3, 4):
        raise ValueError("expected an (H, W, 3) or (H, W, 4) array")
    h, w, c = img.shape
    color_type = COLOR_RGBA if c == 4 else COLOR_RGB
    header = struct.pack(">IIBBBBB", w, h, BIT_DEPTH, color_type, 0, 0, 0)
    rows = np.concatenate([np.full((h, 1), FILTER_NONE, dtype=np.uint8), img.reshape(h, w * c)], axis=1)
    data = zlib.compress(rows.tobytes(), COMPRESSION_LEVEL)
    return SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", data) + _chunk(b"IEND", b"")


def write_png(path: str | os.PathLike, image: np.ndarray) -> None:
    """Write ``image`` to ``path`` as PNG."""
    with open(path, "wb") as fh:
        fh.write(encode_png(image))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw: bytes, h: int, stride: int, bpp: int) -> np.ndarray:
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int32)
    pos = 0
    for y in range(h):
        kind = raw[pos]
        line = np.frombuffer(raw, dtype=np.uint8, count=stride, offset=pos + 1).astype(np.int32)
        pos += stride + 1
        cur = np.zeros(stride, dtype=np.int32)
        if kind == FILTER_NONE:
            cur = line
        elif kind == FILTER_UP:
            cur = (line + prev) & 0xFF
        else:
            for x in range(stride):
                left = cur[x - bpp] if x >= bpp else 0
                up = prev[x]
                upleft = prev[x - bpp] if x >= bpp else 0
                pred = {FILTER_SUB: left, FILTER_AVERAGE: (left + up) // 2,
                        FILTER_PAETH: _paeth(left, up, upleft)}.get(kind)
                if pred is None:
                    raise ValueError(f"unknown PNG filter {kind}")
                cur[x] = (line[x] + pred) & 0xFF
        out[y] = cur
        prev = cur
    return out


def decode_png(data: bytes) -> np.ndarray:
    """Decode a non-interlaced 8-bit RGB/RGBA PNG."""
    if not data.startswith(SIGNATURE):
        raise ValueError("not a PNG file")
    pos = len(SIGNATURE)
    idat = b""
    width = height = color_type = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += length + 12
        if kind == b"IHDR":
            width, height, depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != BIT_DEPTH or color_type not in CHANNELS or interlace:
                raise ValueError("only 8-bit non-interlaced RGB/RGBA PNGs are supported")
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if width is None:
        raise ValueError("missing IHDR")
    channels = CHANNELS[color_type]
    rows = _unfilter(zlib.decompress(idat), height, width * channels, channels)
    return rows.reshape(height, width, channels)


def read_png(path: str | os.PathLike) -> np.ndarray:
    """Read a PNG written by :func:`write_png` (or any 8-bit RGB/RGBA PNG)."""
    with open(path, "rb") as fh:
        return decode_png(fh.read())
