"""feTurbulence: the SVG reference Perlin-noise algorithm (numpy fallback)."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

B_SIZE = 0x100
B_MASK = 0xFF
PERLIN_N = 0x1000
RAND_M = 2147483647
RAND_A = 16807
RAND_Q = 127773
RAND_R = 2836
CHANNELS = 4
PIXEL_CENTER = 0.5


def _setup_seed(seed: int) -> int:
    if seed <= 0:
        seed = -(seed % (RAND_M - 1)) + 1
    if seed > RAND_M - 1:
        seed = RAND_M - 1
    return seed


def _c_mod(a: int, b: int) -> int:
    return int(math.fmod(a, b))


def _random(seed: int) -> int:
    result = RAND_A * _c_mod(seed, RAND_Q) - RAND_R * int(seed / RAND_Q)
    if result <= 0:
        result += RAND_M
    return result


@lru_cache(maxsize=16)
def lattice(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The permutation table and gradient vectors for ``seed``."""
    seed = _setup_seed(seed)
    selector = list(range(B_SIZE + B_SIZE + 2))
    grad = np.zeros((CHANNELS, B_SIZE + B_SIZE + 2, 2), dtype=np.float64)
    for k in range(CHANNELS):
        for i in range(B_SIZE):
            selector[i] = i
            for j in range(2):
                seed = _random(seed)
                grad[k, i, j] = float((seed % (B_SIZE + B_SIZE)) - B_SIZE) / B_SIZE
            norm = math.sqrt(grad[k, i, 0] ** 2 + grad[k, i, 1] ** 2)
            grad[k, i] /= norm
    i = B_SIZE - 1
    while i > 0:
        k = selector[i]
        seed = _random(seed)
        j = seed % B_SIZE
        selector[i] = selector[j]
        selector[j] = k
        i -= 1
    for i in range(B_SIZE + 2):
        selector[B_SIZE + i] = selector[i]
        grad[:, B_SIZE + i] = grad[:, i]
    return np.array(selector, dtype=np.int64), grad


def _noise2(channel: int, vx: np.ndarray, vy: np.ndarray, selector, grad, stitch) -> np.ndarray:
    t = vx + PERLIN_N
    bx0 = t.astype(np.int64) & B_MASK
    bx1 = (bx0 + 1) & B_MASK
    rx0 = t - t.astype(np.int64)
    rx1 = rx0 - 1.0
    t = vy + PERLIN_N
    by0 = t.astype(np.int64) & B_MASK
    by1 = (by0 + 1) & B_MASK
    ry0 = t - t.astype(np.int64)
    ry1 = ry0 - 1.0
    if stitch is not None:
        width, height, wrap_x, wrap_y = stitch
        bx0 = np.where(bx0 >= wrap_x, bx0 - width, bx0)
        bx1 = np.where(bx1 >= wrap_x, bx1 - width, bx1)
        by0 = np.where(by0 >= wrap_y, by0 - height, by0)
        by1 = np.where(by1 >= wrap_y, by1 - height, by1)
    bx0, bx1, by0, by1 = bx0 & B_MASK, bx1 & B_MASK, by0 & B_MASK, by1 & B_MASK
    i, j = selector[bx0], selector[bx1]
    b00, b10 = selector[i + by0], selector[j + by0]
    b01, b11 = selector[i + by1], selector[j + by1]
    sx = rx0 * rx0 * (3.0 - 2.0 * rx0)
    sy = ry0 * ry0 * (3.0 - 2.0 * ry0)
    g = grad[channel]
    u = rx0 * g[b00, 0] + ry0 * g[b00, 1]
    v = rx1 * g[b10, 0] + ry0 * g[b10, 1]
    a = u + sx * (v - u)
    u = rx0 * g[b01, 0] + ry1 * g[b01, 1]
    v = rx1 * g[b11, 0] + ry1 * g[b11, 1]
    b = u + sx * (v - u)
    return a + sy * (b - a)


def stitch_frequencies(fx: float, fy: float, tile: tuple[float, float, float, float]):
    """Adjusted base frequencies and the initial stitch info."""
    tx, ty, tw, th = tile

    def adjust(freq: float, size: float) -> float:
        if freq == 0.0 or size <= 0:
            return freq
        lo = math.floor(size * freq) / size
        hi = math.ceil(size * freq) / size
        return lo if lo > 0 and freq / lo < hi / freq else hi

    fx, fy = adjust(fx, tw), adjust(fy, th)
    width = int(tw * fx + 0.5)
    height = int(th * fy + 0.5)
    wrap_x = int(tx * fx + PERLIN_N + width)
    wrap_y = int(ty * fy + PERLIN_N + height)
    return fx, fy, [width, height, wrap_x, wrap_y]


def py_turbulence(height: int, width: int, inv: np.ndarray, base_fx: float, base_fy: float,
                  octaves: int = 1, seed: int = 0, stitch: bool = False, fractal: bool = False,
                  tile: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)) -> np.ndarray:
    """Premultiplied turbulence image; ``inv`` maps pixels to filter user space."""
    selector, grad = lattice(int(seed))
    py, px = np.mgrid[0:height, 0:width].astype(np.float64)
    px += PIXEL_CENTER
    py += PIXEL_CENTER
    ux = inv[0, 0] * px + inv[0, 1] * py + inv[0, 2]
    uy = inv[1, 0] * px + inv[1, 1] * py + inv[1, 2]
    info = None
    if stitch:
        base_fx, base_fy, info = stitch_frequencies(base_fx, base_fy, tile)
    out = np.zeros((height, width, CHANNELS), dtype=np.float64)
    for ch in range(CHANNELS):
        st = list(info) if info is not None else None
        vx, vy = ux * base_fx, uy * base_fy
        ratio = 1.0
        total = np.zeros_like(vx)
        for _ in range(octaves):
            n = _noise2(ch, vx, vy, selector, grad, st)
            total += (n if fractal else np.abs(n)) / ratio
            vx, vy = vx * 2, vy * 2
            ratio *= 2
            if st is not None:
                st[0] *= 2
                st[2] = 2 * st[2] - PERLIN_N
                st[1] *= 2
                st[3] = 2 * st[3] - PERLIN_N
        out[..., ch] = (total + 1.0) / 2.0 if fractal else total
    out = np.clip(out, 0.0, 1.0)
    out[..., :3] *= out[..., 3:4]
    return out.astype(np.float32)
