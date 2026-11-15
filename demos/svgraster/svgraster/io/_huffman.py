"""Baseline JPEG Huffman tables and entropy decoding (pure Python twin of the Cython codec)."""
from __future__ import annotations

import numpy as np

MAX_CODE_LENGTH = 16
VALUES = 256
# Packed table row: maxcode[0:17], valptr[17:34], mincode[34:51], values[51:307].
MAXCODE, VALPTR, MINCODE, HUFFVAL = 0, 17, 34, 51
TABLE_WIDTH = HUFFVAL + VALUES
COMP_H, COMP_V, COMP_DC, COMP_AC, COMP_BASE, COMP_BW = range(6)
BLOCK = 64
RST0 = 0xD0


def pack_table(counts: list[int], values: list[int]) -> np.ndarray:
    """The JPEG F.2.2.3 decoding arrays for one table, packed into one int32 row."""
    row = np.zeros(TABLE_WIDTH, dtype=np.int32)
    row[MAXCODE:MAXCODE + 17] = -1
    code = k = 0
    for length in range(1, MAX_CODE_LENGTH + 1):
        n = counts[length - 1]
        if n:
            row[VALPTR + length] = k
            row[MINCODE + length] = code
            code += n
            k += n
            row[MAXCODE + length] = code - 1
        code <<= 1
    row[HUFFVAL:HUFFVAL + len(values)] = values[:VALUES]
    return row


class _Bits:
    def __init__(self, data: bytes, pos: int):
        self.data, self.pos, self.acc, self.n = data, pos, 0, 0

    def bit(self) -> int:
        if self.n == 0:
            byte = 0
            if self.pos < len(self.data):
                byte = self.data[self.pos]
                if byte == 0xFF:
                    nxt = self.data[self.pos + 1] if self.pos + 1 < len(self.data) else 0
                    if nxt == 0:
                        self.pos += 2
                    else:
                        byte = 0
                else:
                    self.pos += 1
            self.acc, self.n = byte, 8
        self.n -= 1
        return (self.acc >> self.n) & 1

    def bits(self, count: int) -> int:
        v = 0
        for _ in range(count):
            v = (v << 1) | self.bit()
        return v

    def decode(self, table: np.ndarray) -> int:
        code = 0
        for length in range(1, MAX_CODE_LENGTH + 1):
            code = (code << 1) | self.bit()
            if code <= table[MAXCODE + length]:
                return int(table[HUFFVAL + table[VALPTR + length] + code - table[MINCODE + length]])
        raise ValueError("corrupt JPEG Huffman data")

    def restart(self) -> None:
        self.n = 0
        while self.pos + 1 < len(self.data) and not (self.data[self.pos] == 0xFF and
                                                      RST0 <= self.data[self.pos + 1] <= RST0 + 7):
            self.pos += 1
        self.pos += 2


def _extend(v: int, t: int) -> int:
    return v - (1 << t) + 1 if t and v < (1 << (t - 1)) else v


def py_decode_scan(data: bytes, pos: int, comps: np.ndarray, tables: np.ndarray, coef: np.ndarray,
                   mcux: int, mcuy: int, restart: int) -> int:
    """Decode a baseline scan into ``coef`` (``(blocks, 64)`` int32, zigzag order); returns the end offset.

    ``comps`` rows are ``(h, v, dc table, ac table, first block, blocks per row)``; tables 0-3 are DC,
    4-7 are AC.
    """
    bits = _Bits(data, pos)
    pred = [0] * len(comps)
    count = 0
    for my in range(mcuy):
        for mx in range(mcux):
            if restart and count and count % restart == 0:
                bits.restart()
                pred = [0] * len(comps)
            count += 1
            for ci, (h, v, dc, ac, base, bw) in enumerate(comps):
                for by in range(v):
                    for bx in range(h):
                        block = coef[base + (my * v + by) * bw + mx * h + bx]
                        t = bits.decode(tables[dc])
                        pred[ci] += _extend(bits.bits(t), t)
                        block[0] = pred[ci]
                        k = 1
                        while k < BLOCK:
                            rs = bits.decode(tables[4 + ac])
                            r, s = rs >> 4, rs & 15
                            if s == 0:
                                if r != 15:
                                    break
                                k += 16
                                continue
                            k += r
                            if k < BLOCK:
                                block[k] = _extend(bits.bits(s), s)
                            k += 1
    return bits.pos
