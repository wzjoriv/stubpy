# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, initializedcheck=False
# cython: embedsignature=True, binding=True
"""Gradient paint servers: color ramps and linear/radial gradient fills (Cython, OpenMP)."""
from cython.parallel cimport prange
from libc.math cimport floor, pow, sqrt

import numpy as np

cdef extern from *:
    """
    #ifdef _OPENMP
    #include <omp.h>
    #define SVGR_HAVE_OPENMP 1
    static void svgr_set_threads(int n) { omp_set_num_threads(n); }
    static int svgr_max_threads(void) { return omp_get_max_threads(); }
    #else
    #define SVGR_HAVE_OPENMP 0
    static void svgr_set_threads(int n) { (void)n; }
    static int svgr_max_threads(void) { return 1; }
    #endif
    """
    int SVGR_HAVE_OPENMP
    void svgr_set_threads(int n) nogil
    int svgr_max_threads() nogil

cdef enum Spread:
    SPREAD_PAD = 0
    SPREAD_REFLECT = 1
    SPREAD_REPEAT = 2

PAD = SPREAD_PAD
REFLECT = SPREAD_REFLECT
REPEAT = SPREAD_REPEAT
LUT_SIZE = 1024
HAVE_OPENMP = bool(SVGR_HAVE_OPENMP)

cdef double PIXEL_CENTER = 0.5
cdef double FOCAL_LIMIT = 0.999
cdef double SRGB_KNEE = 0.04045
cdef double LINEAR_KNEE = 0.0031308
cdef double SRGB_SLOPE = 12.92
cdef double SRGB_GAMMA = 2.4
cdef double SRGB_A = 0.055


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


cdef inline double apply_spread(double t, int spread) noexcept nogil:
    cdef double m
    if spread == SPREAD_REPEAT:
        return t - floor(t)
    if spread == SPREAD_REFLECT:
        m = t - 2.0 * floor(t / 2.0)
        return 2.0 - m if m > 1.0 else m
    if t < 0.0:
        return 0.0
    return 1.0 if t > 1.0 else t


cdef inline void lookup(float[:, ::1] lut, double t, float[:, :, ::1] out, Py_ssize_t y, Py_ssize_t x) noexcept nogil:
    cdef Py_ssize_t n = lut.shape[0]
    cdef Py_ssize_t idx = <Py_ssize_t>(t * (n - 1) + PIXEL_CENTER)
    cdef int ch
    if idx < 0:
        idx = 0
    elif idx > n - 1:
        idx = n - 1
    for ch in range(4):
        out[y, x, ch] = lut[idx, ch]


def set_num_threads(int n):
    """Set the OpenMP thread count used by the fills (no-op without OpenMP)."""
    if n > 0:
        svgr_set_threads(n)


def max_threads():
    """The OpenMP thread limit (1 without OpenMP)."""
    return svgr_max_threads()


cdef class GradientLUT:
    """A premultiplied color ramp built from gradient stops."""

    cdef float[:, ::1] _table
    cdef bint _linear

    def __init__(self, double[::1] offsets, double[:, ::1] colors, int size=1024, bint linear_rgb=False):
        cdef Py_ssize_t n = offsets.shape[0], i, j, nxt, ch
        cdef double t, span, frac, value
        cdef double[:, ::1] col
        if size < 2:
            raise ValueError("size must be at least 2")
        if n == 0 or colors.shape[0] != n or colors.shape[1] != 4:
            raise ValueError("offsets and colors must be non-empty and equally long")
        col = np.array(colors, dtype=np.float64)
        if linear_rgb:
            for i in range(n):
                for ch in range(3):
                    col[i, ch] = to_linear(col[i, ch])
        self._table = np.empty((size, 4), dtype=np.float32)
        self._linear = linear_rgb
        for i in range(size):
            t = <double>i / (size - 1)
            j = -1
            while j + 1 < n and offsets[j + 1] <= t:
                j += 1
            if j < 0:
                j = 0
            nxt = j + 1 if j + 1 < n else n - 1
            span = offsets[nxt] - offsets[j]
            frac = (t - offsets[j]) / span if span > 0 else 0.0
            frac = 0.0 if frac < 0.0 else (1.0 if frac > 1.0 else frac)
            for ch in range(4):
                if t < offsets[0]:
                    value = col[0, ch]
                elif t >= offsets[n - 1]:
                    value = col[n - 1, ch]
                else:
                    value = col[j, ch] + (col[nxt, ch] - col[j, ch]) * frac
                if linear_rgb and ch < 3:
                    value = to_srgb(value)
                self._table[i, ch] = <float>value
            for ch in range(3):
                self._table[i, ch] = <float>(<double>self._table[i, ch] * <double>self._table[i, 3])

    @property
    def size(self):
        """Entries in the ramp."""
        return self._table.shape[0]

    @property
    def linear_rgb(self):
        """Whether stops were interpolated in linearRGB."""
        return self._linear

    @property
    def table(self):
        """The ``(size, 4)`` premultiplied float32 ramp."""
        return np.asarray(self._table)

    cpdef tuple sample(self, double t, int spread=SPREAD_PAD):
        """The premultiplied color at parameter ``t``."""
        cdef Py_ssize_t n = self._table.shape[0]
        cdef double tt = apply_spread(t, spread)
        cdef Py_ssize_t idx = <Py_ssize_t>(tt * (n - 1) + PIXEL_CENTER)
        idx = 0 if idx < 0 else (n - 1 if idx > n - 1 else idx)
        return (self._table[idx, 0], self._table[idx, 1], self._table[idx, 2], self._table[idx, 3])

    cpdef void fill_linear(self, float[:, :, ::1] out, double[:, ::1] inv, double x1, double y1,
                           double x2, double y2, int spread=SPREAD_PAD):
        """Fill ``out`` with this ramp along the line ``(x1, y1) -> (x2, y2)``."""
        linear_gradient(out, inv, x1, y1, x2, y2, self._table, spread)


cpdef void linear_gradient(float[:, :, ::1] out, double[:, ::1] inv, double x1, double y1, double x2, double y2,
                           float[:, ::1] lut, int spread=SPREAD_PAD):
    """Fill ``out`` with a linear gradient; ``inv`` maps device pixels to gradient space."""
    cdef Py_ssize_t h = out.shape[0], w = out.shape[1], y, x
    cdef double dx = x2 - x1, dy = y2 - y1, den = dx * dx + dy * dy, px, py, u, v, t
    with nogil:
        for y in prange(h, schedule="static"):
            py = y + PIXEL_CENTER
            for x in range(w):
                px = x + PIXEL_CENTER
                u = inv[0, 0] * px + inv[0, 1] * py + inv[0, 2]
                v = inv[1, 0] * px + inv[1, 1] * py + inv[1, 2]
                t = ((u - x1) * dx + (v - y1) * dy) / den if den > 0 else 1.0
                lookup(lut, apply_spread(t, spread), out, y, x)


cpdef tuple clamp_focal(double cx, double cy, double r, double fx, double fy):
    """Pull the focal point inside the end circle."""
    cdef double ex = fx - cx, ey = fy - cy, dist = sqrt(ex * ex + ey * ey), limit = r * FOCAL_LIMIT
    if dist > limit and dist > 0:
        return (cx + ex * limit / dist, cy + ey * limit / dist)
    return (fx, fy)


cpdef void radial_gradient(float[:, :, ::1] out, double[:, ::1] inv, double cx, double cy, double r,
                           double fx, double fy, float[:, ::1] lut, int spread=SPREAD_PAD):
    """Fill ``out`` with a focal radial gradient; ``inv`` maps device pixels to gradient space."""
    cdef Py_ssize_t h = out.shape[0], w = out.shape[1], y, x
    cdef double px, py, u, v, dx, dy, a, b, c, s, t, ex, ey
    if r <= 0:
        with nogil:
            for y in prange(h, schedule="static"):
                for x in range(w):
                    lookup(lut, 1.0, out, y, x)
        return
    fx, fy = clamp_focal(cx, cy, r, fx, fy)
    ex = fx - cx
    ey = fy - cy
    with nogil:
        for y in prange(h, schedule="static"):
            py = y + PIXEL_CENTER
            for x in range(w):
                px = x + PIXEL_CENTER
                u = inv[0, 0] * px + inv[0, 1] * py + inv[0, 2]
                v = inv[1, 0] * px + inv[1, 1] * py + inv[1, 2]
                dx = u - fx
                dy = v - fy
                a = dx * dx + dy * dy
                b = ex * dx + ey * dy
                c = ex * ex + ey * ey - r * r
                if a > 0:
                    s = b * b - a * c
                    s = (-b + sqrt(s if s > 0 else 0.0)) / a
                    t = 1.0 / s if s > 0 else 1.0
                else:
                    t = 0.0
                lookup(lut, apply_spread(t, spread), out, y, x)
