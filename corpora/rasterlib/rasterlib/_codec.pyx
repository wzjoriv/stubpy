# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, embedsignature=True
"""PNG scanline unfiltering, JPEG Huffman tables and YCbCr conversion (Cython, embedsignature)."""
from libc.stdlib cimport abs as c_abs

import numpy as np

cdef int MAX_CODE_LENGTH = 16
cdef int MAXCODE = 0
cdef int VALPTR = 17
cdef int MINCODE = 34
cdef int HUFFVAL = 51


cpdef enum PngFilter:
    NONE = 0
    SUB = 1
    UP = 2
    AVERAGE = 3
    PAETH = 4


cpdef enum TableClass:
    DC = 0
    AC = 1


class CodecError(ValueError):
    """Raised for corrupt PNG or JPEG data."""


cdef inline int paeth(int a, int b, int c) noexcept nogil:
    cdef int p = a + b - c
    cdef int pa = c_abs(p - a), pb = c_abs(p - b), pc = c_abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def unfilter(const unsigned char[::1] raw, int height, int stride, int bpp):
    """Undo PNG filters on ``height`` rows of ``1 + stride`` bytes; returns ``(height, stride)`` uint8."""
    out_arr = np.zeros((height, stride), dtype=np.uint8)
    cdef unsigned char[:, ::1] out = out_arr
    cdef Py_ssize_t y, x, pos
    cdef int kind, left, up, upleft, pred
    if raw.shape[0] < height * (stride + 1):
        raise CodecError("PNG image data is truncated")
    with nogil:
        for y in range(height):
            pos = y * (stride + 1)
            kind = raw[pos]
            if kind > PAETH:
                with gil:
                    raise CodecError(f"unknown PNG filter type {kind}")
            for x in range(stride):
                left = out[y, x - bpp] if x >= bpp else 0
                up = out[y - 1, x] if y > 0 else 0
                upleft = out[y - 1, x - bpp] if (y > 0 and x >= bpp) else 0
                if kind == SUB:
                    pred = left
                elif kind == UP:
                    pred = up
                elif kind == AVERAGE:
                    pred = (left + up) >> 1
                elif kind == PAETH:
                    pred = paeth(left, up, upleft)
                else:
                    pred = 0
                out[y, x] = <unsigned char>((raw[pos + 1 + x] + pred) & 0xFF)
    return out_arr


cdef class HuffmanTable:
    """A JPEG Huffman table built from the 16 code-length counts and the symbol values."""

    cdef public object counts
    cdef public object values
    cdef readonly TableClass table_class

    def __init__(self, counts, values, TableClass table_class=DC):
        if len(counts) != MAX_CODE_LENGTH:
            raise ValueError("counts must have 16 entries")
        if sum(counts) != len(values):
            raise ValueError("values must match the total of counts")
        self.counts = list(counts)
        self.values = list(values)
        self.table_class = table_class

    @property
    def max_length(self):
        """The longest code length in use."""
        lengths = [i + 1 for i, n in enumerate(self.counts) if n]
        return max(lengths) if lengths else 0

    def packed(self):
        """The F.2.2.3 decoding arrays as one int32 row (``maxcode``, ``valptr``, ``mincode``, values)."""
        row = np.zeros(HUFFVAL + 256, dtype=np.int32)
        row[MAXCODE:MAXCODE + 17] = -1
        code = k = 0
        for length in range(1, MAX_CODE_LENGTH + 1):
            n = self.counts[length - 1]
            if n:
                row[VALPTR + length] = k
                row[MINCODE + length] = code
                code += n
                k += n
                row[MAXCODE + length] = code - 1
            code <<= 1
        row[HUFFVAL:HUFFVAL + len(self.values)] = self.values[:256]
        return row


def ycbcr_to_rgb(double[:, ::1] y, double[:, ::1] cb, double[:, ::1] cr):
    """JFIF YCbCr planes (0-255) to an ``(H, W, 3)`` uint8 RGB array."""
    cdef Py_ssize_t h = y.shape[0], w = y.shape[1], i, j
    cdef double r, g, b, cbv, crv
    out_arr = np.empty((h, w, 3), dtype=np.uint8)
    cdef unsigned char[:, :, ::1] out = out_arr
    with nogil:
        for i in range(h):
            for j in range(w):
                cbv = cb[i, j] - 128.0
                crv = cr[i, j] - 128.0
                r = y[i, j] + 1.402 * crv + 0.5
                g = y[i, j] - 0.344136 * cbv - 0.714136 * crv + 0.5
                b = y[i, j] + 1.772 * cbv + 0.5
                out[i, j, 0] = <unsigned char>(0 if r < 0 else (255 if r > 255 else r))
                out[i, j, 1] = <unsigned char>(0 if g < 0 else (255 if g > 255 else g))
                out[i, j, 2] = <unsigned char>(0 if b < 0 else (255 if b > 255 else b))
    return out_arr
