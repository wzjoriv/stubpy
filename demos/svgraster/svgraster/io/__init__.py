"""Image output: PNG (hand-written zlib encoder), binary PPM and ``.npy``."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from .png import decode_png, encode_png, read_png, write_png

BYTE_MAX = 255.0
PPM_MAXVAL = 255
FORMATS = (".png", ".ppm", ".npy")


def _as_uint8(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint8:
        return image
    return np.floor(np.clip(image, 0.0, 1.0) * BYTE_MAX + 0.5).astype(np.uint8)


def write_ppm(path: str | os.PathLike, image: np.ndarray, background=(255, 255, 255)) -> None:
    """Write binary PPM (P6), compositing any alpha over ``background``."""
    img = _as_uint8(image)
    if img.shape[2] == 4:
        alpha = img[..., 3:4].astype(np.float64) / BYTE_MAX
        rgb = img[..., :3] * alpha + np.asarray(background, dtype=np.float64) * (1 - alpha)
        img = np.floor(rgb + 0.5).astype(np.uint8)
    h, w = img.shape[:2]
    with open(path, "wb") as fh:
        fh.write(f"P6\n{w} {h}\n{PPM_MAXVAL}\n".encode("ascii"))
        fh.write(np.ascontiguousarray(img[..., :3]).tobytes())


def read_ppm(path: str | os.PathLike) -> np.ndarray:
    """Read a binary PPM (P6) written by :func:`write_ppm`."""
    data = Path(path).read_bytes()
    parts = data.split(maxsplit=4)
    if parts[0] != b"P6":
        raise ValueError("not a binary PPM")
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(parts[4][: w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def save(image: np.ndarray, path: str | os.PathLike) -> Path:
    """Save by extension: ``.png``, ``.ppm`` or ``.npy``."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".png":
        write_png(path, _as_uint8(image))
    elif ext == ".ppm":
        write_ppm(path, image)
    elif ext == ".npy":
        np.save(path, image)
    else:
        raise ValueError(f"unsupported output format {ext!r}; use one of {FORMATS}")
    return path


__all__ = ["FORMATS", "decode_png", "encode_png", "read_png", "read_ppm", "save", "write_png", "write_ppm"]
