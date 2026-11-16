"""numba-compiled hot loops with numpy fallbacks: ``downscale`` and ``premultiply_u8``."""
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


def py_downscale(img: np.ndarray, factor: int) -> np.ndarray:
    """Average ``factor x factor`` blocks of an ``(H, W, C)`` float32 image."""
    h, w, c = img.shape
    oh, ow = h // factor, w // factor
    blocks = img[:oh * factor, :ow * factor].reshape(oh, factor, ow, factor, c)
    return blocks.mean(axis=(1, 3), dtype=np.float64).astype(np.float32)


def py_premultiply_u8(img: np.ndarray) -> np.ndarray:
    """uint8 straight alpha to premultiplied float32."""
    out = img.astype(np.float32) / np.float32(BYTE_MAX)
    out[..., :3] *= out[..., 3:4]
    return out


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
    def _premultiply_kernel(img, out):
        h, w, _ = img.shape
        for y in range(h):
            for x in range(w):
                a = img[y, x, 3] / 255.0
                out[y, x, 3] = a
                for ch in range(3):
                    out[y, x, ch] = img[y, x, ch] / 255.0 * a

def premultiply_u8(img: np.ndarray, use_jit: bool = True) -> np.ndarray:
    """uint8 straight-alpha RGBA to premultiplied float32."""
    if HAVE_NUMBA and use_jit:
        src = np.ascontiguousarray(img, dtype=np.uint8)
        out = np.empty(src.shape, dtype=np.float32)
        _premultiply_kernel(src, out)
        return out
    return py_premultiply_u8(img)


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
