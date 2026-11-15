# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, embedsignature=True
"""Image codec hot loops: PNG scanline unfiltering and baseline JPEG entropy decoding (Cython)."""
from libc.stdlib cimport abs as c_abs

import numpy as np

cdef int MAX_CODE_LENGTH = 16
cdef int MAXCODE = 0
cdef int VALPTR = 17
cdef int MINCODE = 34
cdef int HUFFVAL = 51
cdef int BLOCK = 64
cdef int RST0 = 0xD0


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


cdef struct BitReader:
    const unsigned char* data
    Py_ssize_t size
    Py_ssize_t pos
    unsigned int acc
    int n


cdef inline int read_bit(BitReader* br) noexcept nogil:
    cdef unsigned int byte
    if br.n == 0:
        byte = 0
        if br.pos < br.size:
            byte = br.data[br.pos]
            if byte == 0xFF:
                if br.pos + 1 < br.size and br.data[br.pos + 1] == 0:
                    br.pos += 2
                elif br.pos + 1 >= br.size:
                    br.pos += 1
                else:
                    byte = 0
            else:
                br.pos += 1
        br.acc = byte
        br.n = 8
    br.n -= 1
    return (br.acc >> br.n) & 1


cdef inline int read_bits(BitReader* br, int count) noexcept nogil:
    cdef int v = 0, i
    for i in range(count):
        v = (v << 1) | read_bit(br)
    return v


cdef inline int decode_symbol(BitReader* br, const int[::1] table) noexcept nogil:
    cdef int code = 0, length
    for length in range(1, MAX_CODE_LENGTH + 1):
        code = (code << 1) | read_bit(br)
        if code <= table[MAXCODE + length]:
            return table[HUFFVAL + table[VALPTR + length] + code - table[MINCODE + length]]
    return -1


cdef inline int extend(int v, int t) noexcept nogil:
    if t and v < (1 << (t - 1)):
        return v - (1 << t) + 1
    return v


cdef inline void restart(BitReader* br) noexcept nogil:
    br.n = 0
    while br.pos + 1 < br.size and not (br.data[br.pos] == 0xFF and RST0 <= br.data[br.pos + 1] <= RST0 + 7):
        br.pos += 1
    br.pos += 2


def decode_scan(const unsigned char[::1] data, Py_ssize_t pos, const int[:, ::1] comps, const int[:, ::1] tables,
                int[:, ::1] coef, int mcux, int mcuy, int restart_interval):
    """Decode a baseline scan into ``coef`` (zigzag order) and return the offset after it.

    ``comps`` rows are ``(h, v, dc table, ac table, first block, blocks per row)``.
    """
    cdef BitReader br
    cdef int pred[4]
    cdef int ncomp = comps.shape[0], ci, mx, my, bx, by, t, k, rs, r, s, count = 0, bad = 0
    cdef Py_ssize_t block
    if ncomp > 4:
        raise CodecError("too many components in scan")
    br.data = &data[0]
    br.size = data.shape[0]
    br.pos = pos
    br.acc = 0
    br.n = 0
    for ci in range(4):
        pred[ci] = 0
    with nogil:
        for my in range(mcuy):
            for mx in range(mcux):
                if restart_interval and count and count % restart_interval == 0:
                    restart(&br)
                    for ci in range(4):
                        pred[ci] = 0
                count += 1
                for ci in range(ncomp):
                    for by in range(comps[ci, 1]):
                        for bx in range(comps[ci, 0]):
                            block = comps[ci, 4] + (my * comps[ci, 1] + by) * comps[ci, 5] + mx * comps[ci, 0] + bx
                            t = decode_symbol(&br, tables[comps[ci, 2]])
                            if t < 0:
                                bad = 1
                                break
                            pred[ci] += extend(read_bits(&br, t), t)
                            coef[block, 0] = pred[ci]
                            k = 1
                            while k < BLOCK:
                                rs = decode_symbol(&br, tables[4 + comps[ci, 3]])
                                if rs < 0:
                                    bad = 1
                                    break
                                r = rs >> 4
                                s = rs & 15
                                if s == 0:
                                    if r != 15:
                                        break
                                    k += 16
                                    continue
                                k += r
                                if k < BLOCK:
                                    coef[block, k] = extend(read_bits(&br, s), s)
                                k += 1
                            if bad:
                                break
                        if bad:
                            break
                    if bad:
                        break
                if bad:
                    break
            if bad:
                break
    if bad:
        raise CodecError("corrupt JPEG Huffman data")
    return br.pos


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
