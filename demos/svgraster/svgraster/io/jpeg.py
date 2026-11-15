"""A baseline JPEG decoder: Huffman entropy coding, any sampling factors, restart markers, gray and YCbCr."""
from __future__ import annotations

import math
import os
import struct

import numpy as np

from .. import _backend
from ._huffman import BLOCK, pack_table, py_decode_scan

SOI, EOI, SOS, DQT, DHT, DRI = 0xD8, 0xD9, 0xDA, 0xDB, 0xC4, 0xDD
BASELINE_SOF = (0xC0, 0xC1)
UNSUPPORTED_SOF = {0xC2: "progressive", 0xC3: "lossless", 0xC5: "hierarchical", 0xC6: "hierarchical",
                   0xC7: "hierarchical", 0xC9: "arithmetic", 0xCA: "arithmetic progressive",
                   0xCB: "arithmetic lossless"}
APP14 = 0xEE
STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})
LEVEL_SHIFT = 128.0
ZIGZAG = np.array([
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14,
    21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53,
    60, 61, 54, 47, 55, 62, 63])
_U = np.arange(8)
IDCT = (np.where(_U == 0, 1.0 / math.sqrt(2.0), 1.0)[:, None] / 2.0) * np.cos((2 * _U[None, :] + 1) * _U[:, None]
                                                                          * math.pi / 16.0)
CR_R, CB_G, CR_G, CB_B = 1.402, 0.344136, 0.714136, 1.772


class JpegError(ValueError):
    """Raised for corrupt or unsupported JPEG data."""


def decode_scan(data: bytes, pos: int, comps: np.ndarray, tables: np.ndarray, coef: np.ndarray,
                mcux: int, mcuy: int, restart: int) -> int:
    """Entropy-decode one scan, using the Cython codec module when it is built."""
    native = _backend.native("codec")
    if native is None:
        return py_decode_scan(data, pos, comps, tables, coef, mcux, mcuy, restart)
    return native.decode_scan(data, pos, comps, tables, coef, mcux, mcuy, restart)


def _segments(data: bytes):
    if data[:2] != b"\xff\xd8":
        raise JpegError("not a JPEG file")
    pos = 2
    while pos < len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1] if pos + 1 < len(data) else EOI
        pos += 2
        if marker == 0xFF:
            pos -= 1
            continue
        if marker in STANDALONE or marker in (SOI, 0x00):
            continue
        if marker == EOI:
            return
        (length,) = struct.unpack(">H", data[pos:pos + 2])
        yield marker, pos + 2, data[pos + 2:pos + length]
        pos += length


def decode_jpeg(data: bytes) -> np.ndarray:
    """Decode a baseline JPEG into an ``(H, W, 4)`` uint8 RGBA array."""
    qt = np.ones((4, BLOCK), dtype=np.float64)
    tables = np.zeros((8, 307), dtype=np.int32)
    frame = None
    restart = 0
    adobe_transform = None
    coef = None
    for marker, start, body in _segments(data):
        if marker == DQT:
            i = 0
            while i < len(body):
                precision, tq = body[i] >> 4, body[i] & 15
                n = BLOCK * (2 if precision else 1)
                qt[tq & 3] = np.frombuffer(body, ">u2" if precision else "u1", BLOCK, i + 1)
                i += 1 + n
        elif marker == DHT:
            i = 0
            while i < len(body):
                tc, th = body[i] >> 4, body[i] & 15
                counts = list(body[i + 1:i + 17])
                values = list(body[i + 17:i + 17 + sum(counts)])
                tables[(4 if tc else 0) + (th & 3)] = pack_table(counts, values)
                i += 17 + sum(counts)
        elif marker == DRI:
            restart = struct.unpack(">H", body[:2])[0]
        elif marker == APP14 and body[:5] == b"Adobe" and len(body) >= 12:
            adobe_transform = body[11]
        elif marker in UNSUPPORTED_SOF:
            raise JpegError(f"{UNSUPPORTED_SOF[marker]} JPEG is not supported (baseline only)")
        elif marker in BASELINE_SOF:
            precision, height, width, n = struct.unpack(">BHHB", body[:6])
            if precision != 8:
                raise JpegError(f"{precision}-bit JPEG is not supported")
            comps = [(body[6 + 3 * k], body[7 + 3 * k] >> 4, body[7 + 3 * k] & 15, body[8 + 3 * k]) for k in range(n)]
            hmax, vmax = max(c[1] for c in comps), max(c[2] for c in comps)
            mcux, mcuy = math.ceil(width / (8 * hmax)), math.ceil(height / (8 * vmax))
            layout, base = {}, 0
            for cid, h, v, tq in comps:
                layout[cid] = (h, v, tq, base, mcux * h, mcuy * v)
                base += mcux * h * mcuy * v
            coef = np.zeros((base, BLOCK), dtype=np.int32)
            frame = (width, height, comps, hmax, vmax, mcux, mcuy, layout)
        elif marker == SOS:
            if frame is None:
                raise JpegError("scan before frame header")
            width, height, comps, hmax, vmax, mcux, mcuy, layout = frame
            ns = body[0]
            rows = []
            for k in range(ns):
                cid, sel = body[1 + 2 * k], body[2 + 2 * k]
                h, v, _, base, bw, _ = layout[cid]
                rows.append((h, v, sel >> 4, sel & 15, base, bw))
            scan_x, scan_y = mcux, mcuy
            if ns == 1:
                h, v = rows[0][0], rows[0][1]
                scan_x = math.ceil(math.ceil(width * h / hmax) / 8)
                scan_y = math.ceil(math.ceil(height * v / vmax) / 8)
                rows[0] = (1, 1) + rows[0][2:]
            decode_scan(data, start + len(body), np.array(rows, dtype=np.int32), tables, coef, scan_x, scan_y,
                        restart)
    if frame is None or coef is None:
        raise JpegError("JPEG has no frame")
    return _assemble(frame, coef, qt, adobe_transform)


def _assemble(frame, coef: np.ndarray, qt: np.ndarray, adobe_transform) -> np.ndarray:
    width, height, comps, hmax, vmax, mcux, mcuy, layout = frame
    planes = []
    for cid, h, v, tq in comps:
        _, _, _, base, bw, bh = layout[cid]
        blocks = coef[base:base + bw * bh].astype(np.float64) * qt[tq]
        natural = np.empty_like(blocks)
        natural[:, ZIGZAG] = blocks
        pix = np.einsum("vy,nvu,ux->nyx", IDCT, natural.reshape(-1, 8, 8), IDCT) + LEVEL_SHIFT
        plane = pix.reshape(bh, bw, 8, 8).transpose(0, 2, 1, 3).reshape(bh * 8, bw * 8)
        plane = np.repeat(np.repeat(plane, vmax // v, axis=0), hmax // h, axis=1)
        planes.append(plane[:height, :width])
    out = np.empty((height, width, 4), dtype=np.uint8)
    out[..., 3] = 255
    if len(planes) == 1:
        out[..., :3] = np.clip(np.rint(planes[0]), 0, 255)[..., None].astype(np.uint8)
    elif len(planes) == 3:
        if adobe_transform == 0:
            rgb = np.stack(planes, axis=-1)
        else:
            y, cb, cr = planes[0], planes[1] - LEVEL_SHIFT, planes[2] - LEVEL_SHIFT
            rgb = np.stack([y + CR_R * cr, y - CB_G * cb - CR_G * cr, y + CB_B * cb], axis=-1)
        out[..., :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    else:
        raise JpegError(f"{len(planes)}-component (CMYK) JPEG is not supported")
    return out


def read_jpeg(path: str | os.PathLike) -> np.ndarray:
    """Read a JPEG file into RGBA uint8."""
    with open(path, "rb") as fh:
        return decode_jpeg(fh.read())
