"""numba-compiled hot loops with numpy fallbacks.

``downscale`` box-filters a supersampled render, ``unpremultiply`` converts
premultiplied float32 pixels to straight alpha, ``premultiply_u8`` turns decoded
8-bit images into premultiplied float32 and ``resample`` resizes bilinearly.
All are JIT-compiled when numba is importable.
"""
from __future__ import annotations

import numpy as np

try:
    import numba

    HAVE_NUMBA = True
    NUMBA_ERROR: str | None = None
except ImportError as exc:
    numba = None
    HAVE_NUMBA = False
    NUMBA_ERROR = str(exc)

CHANNELS = 4
BYTE_MAX = 255.0
PIXEL_CENTER = 0.5


def py_downscale(img: np.ndarray, factor: int) -> np.ndarray:
    """Average ``factor x factor`` blocks of an ``(H, W, C)`` float32 image."""
    h, w, c = img.shape
    oh, ow = h // factor, w // factor
    blocks = img[:oh * factor, :ow * factor].reshape(oh, factor, ow, factor, c)
    return blocks.mean(axis=(1, 3), dtype=np.float64).astype(np.float32)


def py_unpremultiply(img: np.ndarray) -> np.ndarray:
    """Straight-alpha copy of a premultiplied image."""
    out = img.astype(np.float32, copy=True)
    alpha = out[..., 3:4]
    out[..., :3] = np.where(alpha > 0, out[..., :3] / np.where(alpha > 0, alpha, 1.0), 0.0)
    return out


def py_premultiply_u8(img: np.ndarray) -> np.ndarray:
    """uint8 straight alpha to premultiplied float32."""
    out = img.astype(np.float32) / np.float32(BYTE_MAX)
    out[..., :3] *= out[..., 3:4]
    return out


def py_resample(img: np.ndarray, height: int, width: int) -> np.ndarray:
    """Bilinear resize with pixel centres mapped onto each other and clamped edges."""
    h, w = img.shape[:2]
    ys = np.clip((np.arange(height) + PIXEL_CENTER) * h / height - PIXEL_CENTER, 0, h - 1)
    xs = np.clip((np.arange(width) + PIXEL_CENTER) * w / width - PIXEL_CENTER, 0, w - 1)
    y0, x0 = np.floor(ys).astype(np.int64), np.floor(xs).astype(np.int64)
    y1, x1 = np.minimum(y0 + 1, h - 1), np.minimum(x0 + 1, w - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    src = img.astype(np.float32)
    top = src[y0][:, x0] * (1 - fx) + src[y0][:, x1] * fx
    bottom = src[y1][:, x0] * (1 - fx) + src[y1][:, x1] * fx
    return (top * (1 - fy) + bottom * fy).astype(np.float32)


if HAVE_NUMBA:
    @numba.njit(cache=False, nogil=True)
    def _downscale_kernel(img, factor, out):
        oh, ow, c = out.shape
        inv = 1.0 / (factor * factor)
        for y in range(oh):
            for x in range(ow):
                for ch in range(c):
                    acc = 0.0
                    for dy in range(factor):
                        for dx in range(factor):
                            acc += img[y * factor + dy, x * factor + dx, ch]
                    out[y, x, ch] = acc * inv

    @numba.njit(cache=False, nogil=True)
    def _unpremultiply_kernel(img, out):
        h, w, _ = img.shape
        for y in range(h):
            for x in range(w):
                a = img[y, x, 3]
                out[y, x, 3] = a
                for ch in range(3):
                    out[y, x, ch] = img[y, x, ch] / a if a > 0 else 0.0


    @numba.njit(cache=False, nogil=True)
    def _premultiply_kernel(img, out):
        h, w, _ = img.shape
        for y in range(h):
            for x in range(w):
                a = img[y, x, 3] / 255.0
                out[y, x, 3] = a
                for ch in range(3):
                    out[y, x, ch] = img[y, x, ch] / 255.0 * a

    @numba.njit(cache=False, nogil=True)
    def _resample_kernel(img, out):
        h, w, c = img.shape
        oh, ow, _ = out.shape
        for y in range(oh):
            sy = min(max((y + 0.5) * h / oh - 0.5, 0.0), h - 1.0)
            y0 = int(sy)
            y1 = min(y0 + 1, h - 1)
            fy = sy - y0
            for x in range(ow):
                sx = min(max((x + 0.5) * w / ow - 0.5, 0.0), w - 1.0)
                x0 = int(sx)
                x1 = min(x0 + 1, w - 1)
                fx = sx - x0
                for ch in range(c):
                    top = img[y0, x0, ch] * (1 - fx) + img[y0, x1, ch] * fx
                    bottom = img[y1, x0, ch] * (1 - fx) + img[y1, x1, ch] * fx
                    out[y, x, ch] = top * (1 - fy) + bottom * fy


def premultiply_u8(img: np.ndarray, use_jit: bool = True) -> np.ndarray:
    """uint8 straight-alpha RGBA to premultiplied float32."""
    if HAVE_NUMBA and use_jit:
        src = np.ascontiguousarray(img, dtype=np.uint8)
        out = np.empty(src.shape, dtype=np.float32)
        _premultiply_kernel(src, out)
        return out
    return py_premultiply_u8(img)


def resample(img: np.ndarray, height: int, width: int, use_jit: bool = True) -> np.ndarray:
    """Bilinear resize of an ``(H, W, C)`` float32 image."""
    if height <= 0 or width <= 0:
        raise ValueError("size must be positive")
    if HAVE_NUMBA and use_jit:
        out = np.empty((height, width, img.shape[2]), dtype=np.float32)
        _resample_kernel(np.ascontiguousarray(img, dtype=np.float32), out)
        return out
    return py_resample(img, height, width)


def downscale(img: np.ndarray, factor: int, use_jit: bool = True) -> np.ndarray:
    """Box-filter downscale by an integer ``factor``."""
    if factor <= 1:
        return img
    if HAVE_NUMBA and use_jit:
        h, w, c = img.shape
        out = np.empty((h // factor, w // factor, c), dtype=np.float32)
        _downscale_kernel(np.ascontiguousarray(img, dtype=np.float32), factor, out)
        return out
    return py_downscale(img, factor)


def unpremultiply(img: np.ndarray, use_jit: bool = True) -> np.ndarray:
    """Straight-alpha copy of a premultiplied float32 image."""
    if HAVE_NUMBA and use_jit:
        src = np.ascontiguousarray(img, dtype=np.float32)
        out = np.empty_like(src)
        _unpremultiply_kernel(src, out)
        return out
    return py_unpremultiply(img)
