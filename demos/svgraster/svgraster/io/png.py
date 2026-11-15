"""PNG encoding (8-bit RGB/RGBA) and decoding of every PNG color type, depth and Adam7 (zlib only)."""
from __future__ import annotations

import os
import struct
import zlib

import numpy as np

from .. import _backend

SIGNATURE = b"\x89PNG\r\n\x1a\n"
BIT_DEPTH = 8
COLOR_GRAY = 0
COLOR_RGB = 2
COLOR_PALETTE = 3
COLOR_GRAY_ALPHA = 4
COLOR_RGBA = 6
FILTER_NONE = 0
FILTER_SUB = 1
FILTER_UP = 2
FILTER_AVERAGE = 3
FILTER_PAETH = 4
COMPRESSION_LEVEL = 6
CHANNELS = {COLOR_GRAY: 1, COLOR_RGB: 3, COLOR_PALETTE: 1, COLOR_GRAY_ALPHA: 2, COLOR_RGBA: 4}
VALID_DEPTHS = {COLOR_GRAY: (1, 2, 4, 8, 16), COLOR_RGB: (8, 16), COLOR_PALETTE: (1, 2, 4, 8),
                COLOR_GRAY_ALPHA: (8, 16), COLOR_RGBA: (8, 16)}
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
MAX_PIXELS = 1 << 28
DISPLAY_GAMMA = 2.2
GAMMA_EPSILON = 0.01
GAMMA_SCALE = 100000.0


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


def py_unfilter(raw: bytes, height: int, stride: int, bpp: int) -> np.ndarray:
    """Undo PNG scanline filters; ``raw`` holds ``height`` rows of ``1 + stride`` bytes."""
    if len(raw) < height * (stride + 1):
        raise ValueError("PNG image data is truncated")
    rows = np.frombuffer(raw, dtype=np.uint8, count=height * (stride + 1)).reshape(height, stride + 1)
    out = np.zeros((height, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int32)
    for y in range(height):
        kind = int(rows[y, 0])
        line = rows[y, 1:].astype(np.int32)
        if kind == FILTER_NONE:
            cur = line
        elif kind == FILTER_UP:
            cur = (line + prev) & 0xFF
        elif kind == FILTER_SUB:
            lanes = np.zeros(stride + (-stride) % bpp, dtype=np.int32)
            lanes[:stride] = line
            cur = (np.cumsum(lanes.reshape(-1, bpp), axis=0).reshape(-1)[:stride]) & 0xFF
        elif kind in (FILTER_AVERAGE, FILTER_PAETH):
            cur = np.zeros(stride, dtype=np.int32)
            for x in range(stride):
                left = int(cur[x - bpp]) if x >= bpp else 0
                up = int(prev[x])
                if kind == FILTER_AVERAGE:
                    pred = (left + up) >> 1
                else:
                    pred = _paeth(left, up, int(prev[x - bpp]) if x >= bpp else 0)
                cur[x] = (int(line[x]) + pred) & 0xFF
        else:
            raise ValueError(f"unknown PNG filter type {kind}")
        out[y] = cur
        prev = cur.astype(np.int32)
    return out


def unfilter(raw: bytes, height: int, stride: int, bpp: int) -> np.ndarray:
    """:func:`py_unfilter` through the Cython codec module when it is built."""
    native = _backend.native("codec")
    if native is None:
        return py_unfilter(raw, height, stride, bpp)
    if len(raw) < height * (stride + 1):
        raise ValueError("PNG image data is truncated")
    return native.unfilter(raw, height, stride, bpp)


def _samples(rows: np.ndarray, width: int, channels: int, depth: int) -> np.ndarray:
    h = rows.shape[0]
    if depth == 16:
        return rows.view(">u2")[:, :width * channels].reshape(h, width, channels).astype(np.uint16)
    if depth == 8:
        return rows[:, :width * channels].reshape(h, width, channels)
    bits = np.unpackbits(rows, axis=1)
    per = 8 // depth
    vals = bits.reshape(h, -1, depth)
    weights = (1 << np.arange(depth - 1, -1, -1)).astype(np.uint8)
    return (vals * weights).sum(axis=2).astype(np.uint8)[:, :width * per][:, :width].reshape(h, width, 1)


def _gamma_table(gamma: float | None) -> np.ndarray | None:
    """An 8-bit lookup that maps file samples with ``gAMA`` to sRGB-like display values."""
    if gamma is None or gamma <= 0 or abs(gamma * DISPLAY_GAMMA - 1.0) < GAMMA_EPSILON:
        return None
    levels = np.arange(256) / 255.0
    return np.clip(np.rint(255.0 * levels ** (1.0 / (gamma * DISPLAY_GAMMA))), 0, 255).astype(np.uint8)


def _to_rgba8(samples: np.ndarray, color_type: int, depth: int, palette, trns) -> np.ndarray:
    if color_type == COLOR_PALETTE:
        if palette is None:
            raise ValueError("palette PNG without a PLTE chunk")
        lut = np.zeros((256, 4), dtype=np.uint8)
        lut[:, 3] = 255
        lut[:len(palette), :3] = palette
        if trns is not None:
            alpha = np.frombuffer(trns, dtype=np.uint8)[:256]
            lut[:len(alpha), 3] = alpha
        return lut[samples[..., 0]]
    max_val = (1 << depth) - 1
    key = None
    if trns is not None and color_type in (COLOR_GRAY, COLOR_RGB):
        key = np.array(struct.unpack(f">{len(trns) // 2}H", trns[:len(trns) // 2 * 2]))
    scaled = (samples.astype(np.uint32) * 255 + max_val // 2) // max_val
    h, w, _ = samples.shape
    out = np.empty((h, w, 4), dtype=np.uint8)
    if color_type in (COLOR_GRAY, COLOR_GRAY_ALPHA):
        out[..., :3] = scaled[..., :1]
        out[..., 3] = scaled[..., 1] if color_type == COLOR_GRAY_ALPHA else 255
        if key is not None:
            out[..., 3] = np.where(samples[..., 0] == key[0], 0, out[..., 3])
    else:
        out[..., :3] = scaled[..., :3]
        out[..., 3] = scaled[..., 3] if color_type == COLOR_RGBA else 255
        if key is not None and len(key) >= 3:
            out[..., 3] = np.where(np.all(samples[..., :3] == key[:3], axis=-1), 0, out[..., 3])
    return out


def _read_chunks(data: bytes):
    if not data.startswith(SIGNATURE):
        raise ValueError("not a PNG file")
    pos = len(SIGNATURE)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        yield kind, data[pos + 8:pos + 8 + length]
        pos += length + 12
        if kind == b"IEND":
            return


def decode_png_rgba(data: bytes) -> np.ndarray:
    """Decode any PNG into an ``(H, W, 4)`` uint8 straight-alpha array."""
    header = palette = trns = gamma = None
    idat = []
    for kind, body in _read_chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body[:13])
        elif kind == b"PLTE":
            palette = np.frombuffer(body, dtype=np.uint8)[:len(body) // 3 * 3].reshape(-1, 3)
        elif kind == b"tRNS":
            trns = body
        elif kind == b"gAMA" and len(body) == 4:
            gamma = struct.unpack(">I", body)[0] / GAMMA_SCALE
        elif kind == b"IDAT":
            idat.append(body)
    if header is None:
        raise ValueError("PNG is missing its IHDR chunk")
    width, height, depth, color_type, _, _, interlace = header
    if color_type not in CHANNELS or depth not in VALID_DEPTHS[color_type]:
        raise ValueError(f"invalid PNG color type {color_type} with bit depth {depth}")
    if width == 0 or height == 0 or width * height > MAX_PIXELS:
        raise ValueError(f"unsupported PNG size {width}x{height}")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise ValueError(f"corrupt PNG image data: {exc}") from None
    channels = CHANNELS[color_type]
    bits_pp = channels * depth
    bpp = max(1, bits_pp // 8)
    table = _gamma_table(gamma)
    if not interlace:
        stride = (width * bits_pp + 7) // 8
        rows = unfilter(raw, height, stride, bpp)
        return _apply_gamma(_to_rgba8(_samples(rows, width, channels, depth), color_type, depth, palette, trns),
                            table)
    out = np.zeros((height, width, 4), dtype=np.uint8)
    pos = 0
    for x0, y0, dx, dy in ADAM7:
        pw, ph = (width - x0 + dx - 1) // dx, (height - y0 + dy - 1) // dy
        if pw <= 0 or ph <= 0:
            continue
        stride = (pw * bits_pp + 7) // 8
        size = ph * (stride + 1)
        rows = unfilter(raw[pos:pos + size], ph, stride, bpp)
        pos += size
        out[y0::dy, x0::dx] = _to_rgba8(_samples(rows, pw, channels, depth), color_type, depth, palette, trns)
    return _apply_gamma(out, table)


def _apply_gamma(rgba: np.ndarray, table: np.ndarray | None) -> np.ndarray:
    if table is not None:
        rgba[..., :3] = table[rgba[..., :3]]
    return rgba


def decode_png(data: bytes) -> np.ndarray:
    """Decode a PNG to uint8 RGB (opaque, no transparency key) or RGBA."""
    rgba = decode_png_rgba(data)
    header = next(body for kind, body in _read_chunks(data) if kind == b"IHDR")
    color_type = header[9]
    has_trns = any(kind == b"tRNS" for kind, _ in _read_chunks(data))
    if color_type in (COLOR_GRAY, COLOR_RGB, COLOR_PALETTE) and not has_trns:
        return np.ascontiguousarray(rgba[..., :3])
    return rgba


def read_png(path: str | os.PathLike) -> np.ndarray:
    """Read a PNG file (see :func:`decode_png`)."""
    with open(path, "rb") as fh:
        return decode_png(fh.read())
