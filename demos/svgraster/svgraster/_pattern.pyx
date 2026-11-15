# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, initializedcheck=False
"""Pattern tiling, image resampling and sRGB/linearRGB conversion of premultiplied images (Cython, OpenMP)."""
from cython.parallel cimport prange
from libc.math cimport floor, pow

import numpy as np

cdef extern from *:
    """
    #ifdef _OPENMP
    #include <omp.h>
    #define SVGR_PATTERN_OPENMP 1
    static void svgr_pattern_threads(int n) { omp_set_num_threads(n); }
    #else
    #define SVGR_PATTERN_OPENMP 0
    static void svgr_pattern_threads(int n) { (void)n; }
    #endif
    """
    int SVGR_PATTERN_OPENMP
    void svgr_pattern_threads(int n) nogil

HAVE_OPENMP = bool(SVGR_PATTERN_OPENMP)

cdef double PIXEL_CENTER = 0.5
cdef double SRGB_KNEE = 0.04045
cdef double LINEAR_KNEE = 0.0031308
cdef double SRGB_SLOPE = 12.92
cdef double SRGB_GAMMA = 2.4
cdef double SRGB_A = 0.055


def set_num_threads(int n):
    """Set the OpenMP thread count (no-op without OpenMP)."""
    if n > 0:
        svgr_pattern_threads(n)


cdef inline Py_ssize_t index(Py_ssize_t i, Py_ssize_t n, bint repeat) noexcept nogil:
    if repeat:
        i = i % n
        return i + n if i < 0 else i
    return 0 if i < 0 else (n - 1 if i > n - 1 else i)


cdef void sample(float[:, :, ::1] out, float[:, :, ::1] img, double[:, ::1] inv, bint bilinear,
                 bint repeat) noexcept nogil:
    cdef Py_ssize_t h = out.shape[0], w = out.shape[1], ih = img.shape[0], iw = img.shape[1]
    cdef Py_ssize_t y, x, ch, x0, y0, xa, xb, ya, yb
    cdef double px, py, u, v, fx, fy
    for y in prange(h, schedule="static"):
        py = y + PIXEL_CENTER
        for x in range(w):
            px = x + PIXEL_CENTER
            u = inv[0, 0] * px + inv[0, 1] * py + inv[0, 2]
            v = inv[1, 0] * px + inv[1, 1] * py + inv[1, 2]
            if not bilinear:
                xa = index(<Py_ssize_t>floor(u), iw, repeat)
                ya = index(<Py_ssize_t>floor(v), ih, repeat)
                for ch in range(4):
                    out[y, x, ch] = img[ya, xa, ch]
                continue
            u = u - PIXEL_CENTER
            v = v - PIXEL_CENTER
            x0 = <Py_ssize_t>floor(u)
            y0 = <Py_ssize_t>floor(v)
            fx = u - x0
            fy = v - y0
            xa = index(x0, iw, repeat)
            xb = index(x0 + 1, iw, repeat)
            ya = index(y0, ih, repeat)
            yb = index(y0 + 1, ih, repeat)
            for ch in range(4):
                out[y, x, ch] = <float>((img[ya, xa, ch] * (1 - fx) + img[ya, xb, ch] * fx) * (1 - fy)
                                        + (img[yb, xa, ch] * (1 - fx) + img[yb, xb, ch] * fx) * fy)


def pattern_fill(float[:, :, ::1] out, float[:, :, ::1] tile, double[:, ::1] inv, bint bilinear=True):
    """Tile ``tile`` across ``out``; ``inv`` maps device pixels to tile pixels."""
    if tile.shape[0] == 0 or tile.shape[1] == 0:
        raise ValueError("tile must not be empty")
    with nogil:
        sample(out, tile, inv, bilinear, True)


def sample_image(float[:, :, ::1] out, float[:, :, ::1] img, double[:, ::1] inv, *, bint bilinear=True,
                 bint repeat=False):
    """Resample ``img`` into ``out`` through the device-to-image map ``inv`` (edges clamp unless ``repeat``)."""
    if img.shape[0] == 0 or img.shape[1] == 0:
        raise ValueError("img must not be empty")
    with nogil:
        sample(out, img, inv, bilinear, repeat)


cdef inline double to_linear(double c) noexcept nogil:
    if c <= SRGB_KNEE:
        return c / SRGB_SLOPE
    return pow((c + SRGB_A) / (1.0 + SRGB_A), SRGB_GAMMA)


cdef inline double to_srgb(double c) noexcept nogil:
    if c < 0.0:
        c = 0.0
    if c <= LINEAR_KNEE:
        return c * SRGB_SLOPE
    return (1.0 + SRGB_A) * pow(c, 1.0 / SRGB_GAMMA) - SRGB_A


cdef void convert(float[:, :, ::1] img, bint linear) noexcept nogil:
    cdef Py_ssize_t h = img.shape[0], w = img.shape[1], y, x, ch
    cdef double a, c
    for y in prange(h, schedule="static"):
        for x in range(w):
            a = img[y, x, 3]
            for ch in range(3):
                if a > 0:
                    c = img[y, x, ch] / a
                    c = to_linear(c) if linear else to_srgb(c)
                    img[y, x, ch] = <float>(c * a)
                else:
                    img[y, x, ch] = 0.0


def srgb_to_linear(float[:, :, ::1] img):
    """Convert a premultiplied sRGB image to linearRGB in place."""
    convert(img, True)


def linear_to_srgb(float[:, :, ::1] img):
    """Convert a premultiplied linearRGB image to sRGB in place."""
    convert(img, False)


cdef class PatternTile:
    """A pattern tile image that can be repeated across output buffers."""

    cdef float[:, :, ::1] _tile

    def __init__(self, float[:, :, ::1] tile):
        if tile.shape[0] == 0 or tile.shape[1] == 0 or tile.shape[2] != 4:
            raise ValueError("tile must be a non-empty (h, w, 4) float32 array")
        self._tile = tile

    @property
    def width(self):
        """Tile width in pixels."""
        return self._tile.shape[1]

    @property
    def height(self):
        """Tile height in pixels."""
        return self._tile.shape[0]

    @property
    def image(self):
        """The tile pixels."""
        return np.asarray(self._tile)

    cpdef fill(self, float[:, :, ::1] out, double[:, ::1] inv, bint bilinear=True):
        """Repeat the tile across ``out`` using the device-to-tile map ``inv``."""
        pattern_fill(out, self._tile, inv, bilinear)
