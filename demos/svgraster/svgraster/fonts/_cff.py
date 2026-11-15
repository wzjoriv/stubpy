"""CFF (OpenType ``CFF `` table) outlines: INDEX/DICT parsing and Type 2 charstrings."""
from __future__ import annotations

import struct

from ..parse.pathdata import Path
from ._reader import FontFormatError

OP_CHARSTRINGS = 17
OP_PRIVATE = 18
OP_SUBRS = 19
OP_ESCAPE = 12
OP_FDARRAY = 1236
OP_FDSELECT = 1237
MAX_SUBR_DEPTH = 10
SMALL_BIAS, MEDIUM_BIAS, LARGE_BIAS = 107, 1131, 32768
SMALL_LIMIT, MEDIUM_LIMIT = 1240, 33900
NIBBLES = "0123456789.EE?-"


def read_index(data: bytes, pos: int) -> tuple[list[bytes], int]:
    """The items of a CFF INDEX at ``pos`` and the offset just past it."""
    count = struct.unpack_from(">H", data, pos)[0]
    if count == 0:
        return [], pos + 2
    off_size = data[pos + 2]
    base = pos + 3
    offsets = [int.from_bytes(data[base + i * off_size:base + (i + 1) * off_size], "big") for i in range(count + 1)]
    start = base + (count + 1) * off_size - 1
    items = [data[start + offsets[i]:start + offsets[i + 1]] for i in range(count)]
    return items, start + offsets[-1]


def _real(data: bytes, pos: int) -> tuple[float, int]:
    text = ""
    while True:
        byte = data[pos]
        pos += 1
        for nib in (byte >> 4, byte & 0xF):
            if nib == 0xF:
                try:
                    return float(text or 0), pos
                except ValueError:
                    return 0.0, pos
            text += "E-" if nib == 0xC else NIBBLES[nib]


def read_dict(data: bytes) -> dict[int, list[float]]:
    """A CFF DICT as ``{operator: operands}``; escaped operators are ``1200 + b1``."""
    out: dict[int, list[float]] = {}
    operands: list[float] = []
    pos = 0
    while pos < len(data):
        b0 = data[pos]
        pos += 1
        if b0 <= 21:
            op = b0
            if b0 == OP_ESCAPE:
                op = 1200 + data[pos]
                pos += 1
            out[op] = operands
            operands = []
        elif b0 == 28:
            operands.append(struct.unpack_from(">h", data, pos)[0])
            pos += 2
        elif b0 == 29:
            operands.append(struct.unpack_from(">i", data, pos)[0])
            pos += 4
        elif b0 == 30:
            value, pos = _real(data, pos)
            operands.append(value)
        elif 32 <= b0 <= 246:
            operands.append(b0 - 139)
        elif 247 <= b0 <= 250:
            operands.append((b0 - 247) * 256 + data[pos] + 108)
            pos += 1
        elif 251 <= b0 <= 254:
            operands.append(-(b0 - 251) * 256 - data[pos] - 108)
            pos += 1
    return out


def subr_bias(count: int) -> int:
    """The Type 2 subroutine number bias."""
    return SMALL_BIAS if count < SMALL_LIMIT else MEDIUM_BIAS if count < MEDIUM_LIMIT else LARGE_BIAS


class CffOutlines:
    """Glyph outlines from a ``CFF `` table (name-keyed or CID-keyed)."""

    def __init__(self, data: bytes, offset: int):
        cff = data[offset:]
        if len(cff) < 4:
            raise FontFormatError("CFF table too short")
        pos = cff[2]
        _, pos = read_index(cff, pos)
        top_dicts, pos = read_index(cff, pos)
        _, pos = read_index(cff, pos)
        self.global_subrs, _ = read_index(cff, pos)
        if not top_dicts:
            raise FontFormatError("CFF has no Top DICT")
        top = read_dict(top_dicts[0])
        if OP_CHARSTRINGS not in top:
            raise FontFormatError("CFF has no CharStrings")
        self.charstrings, _ = read_index(cff, int(top[OP_CHARSTRINGS][0]))
        self.cff = cff
        if OP_FDARRAY in top:
            fd_dicts, _ = read_index(cff, int(top[OP_FDARRAY][0]))
            self.fd_subrs = [self._private_subrs(read_dict(fd)) for fd in fd_dicts]
            self.fd_select = self._fd_select(int(top.get(OP_FDSELECT, [0])[0]))
        else:
            self.fd_subrs = [self._private_subrs(top)]
            self.fd_select = None

    def _private_subrs(self, d: dict) -> list[bytes]:
        if OP_PRIVATE not in d or len(d[OP_PRIVATE]) < 2:
            return []
        size, off = int(d[OP_PRIVATE][0]), int(d[OP_PRIVATE][1])
        private = read_dict(self.cff[off:off + size])
        if OP_SUBRS not in private:
            return []
        subrs, _ = read_index(self.cff, off + int(private[OP_SUBRS][0]))
        return subrs

    def _fd_select(self, pos: int) -> list[int]:
        n = len(self.charstrings)
        fmt = self.cff[pos]
        if fmt == 0:
            return list(self.cff[pos + 1:pos + 1 + n])
        out = [0] * n
        count = struct.unpack_from(">H", self.cff, pos + 1)[0]
        for i in range(count):
            first, fd = struct.unpack_from(">HB", self.cff, pos + 3 + 3 * i)
            last = struct.unpack_from(">H", self.cff, pos + 3 + 3 * (i + 1))[0]
            out[first:last] = [fd] * max(0, min(last, n) - first)
        return out

    def outline(self, gid: int) -> Path:
        """The glyph as a cubic path in font units (y up)."""
        if not 0 <= gid < len(self.charstrings):
            return Path()
        fd = self.fd_select[gid] if self.fd_select is not None and gid < len(self.fd_select) else 0
        local = self.fd_subrs[fd] if fd < len(self.fd_subrs) else []
        return Type2Interpreter(self.global_subrs, local).run(self.charstrings[gid])


class Type2Interpreter:
    """Executes a Type 2 charstring into a :class:`Path`."""

    def __init__(self, global_subrs: list[bytes], local_subrs: list[bytes]):
        self.gsubrs, self.lsubrs = global_subrs, local_subrs
        self.gbias, self.lbias = subr_bias(len(global_subrs)), subr_bias(len(local_subrs))
        self.path = Path()
        self.stack: list[float] = []
        self.x = self.y = 0.0
        self.stems = 0
        self.open = False
        self.width_done = False
        self.ended = False

    def run(self, code: bytes) -> Path:
        """Run ``code`` and return the outline."""
        self._exec(code, 0)
        if self.open:
            self.path.close()
        return self.path

    def _move(self, dx: float, dy: float) -> None:
        if self.open:
            self.path.close()
        self.x += dx
        self.y += dy
        self.path.move_to(self.x, self.y)
        self.open = True

    def _line(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy
        self.path.line_to(self.x, self.y)

    def _curve(self, dxa, dya, dxb, dyb, dxc, dyc) -> None:
        x1, y1 = self.x + dxa, self.y + dya
        x2, y2 = x1 + dxb, y1 + dyb
        self.x, self.y = x2 + dxc, y2 + dyc
        self.path.cubic_to(x1, y1, x2, y2, self.x, self.y)

    def _strip_width(self, expected_even: bool, count: int | None = None) -> list[float]:
        args = self.stack
        if not self.width_done:
            self.width_done = True
            if (count is not None and len(args) > count) or (expected_even and len(args) % 2):
                args = args[1:]
        return args

    def _exec(self, code: bytes, depth: int) -> None:
        if depth > MAX_SUBR_DEPTH:
            raise FontFormatError("CFF subroutines nest too deeply")
        pos, n = 0, len(code)
        while pos < n and not self.ended:
            b0 = code[pos]
            pos += 1
            if b0 >= 32 or b0 == 28:
                if b0 == 28:
                    self.stack.append(struct.unpack_from(">h", code, pos)[0])
                    pos += 2
                elif b0 <= 246:
                    self.stack.append(b0 - 139)
                elif b0 <= 250:
                    self.stack.append((b0 - 247) * 256 + code[pos] + 108)
                    pos += 1
                elif b0 <= 254:
                    self.stack.append(-(b0 - 251) * 256 - code[pos] - 108)
                    pos += 1
                else:
                    self.stack.append(struct.unpack_from(">i", code, pos)[0] / 65536.0)
                    pos += 4
                continue
            if b0 == OP_ESCAPE:
                self._flex(code[pos])
                pos += 1
                self.stack = []
                continue
            if b0 in (10, 29):
                index = int(self.stack.pop()) + (self.lbias if b0 == 10 else self.gbias)
                subrs = self.lsubrs if b0 == 10 else self.gsubrs
                if 0 <= index < len(subrs):
                    self._exec(subrs[index], depth + 1)
                continue
            if b0 == 11:
                return
            if b0 in (19, 20):
                args = self._strip_width(True)
                self.stems += len(args) // 2
                pos += (self.stems + 7) // 8
                self.stack = []
                continue
            self._operator(b0)
            self.stack = []

    def _operator(self, op: int) -> None:
        s = self.stack
        if op in (1, 3, 18, 23):
            self.stems += len(self._strip_width(True)) // 2
        elif op == 21:
            args = self._strip_width(False, 2)
            self._move(args[-2], args[-1])
        elif op in (4, 22):
            args = self._strip_width(False, 1)
            self._move(args[-1], 0) if op == 22 else self._move(0, args[-1])
        elif op == 5:
            for i in range(0, len(s) - 1, 2):
                self._line(s[i], s[i + 1])
        elif op in (6, 7):
            horizontal = op == 6
            for v in s:
                self._line(v, 0) if horizontal else self._line(0, v)
                horizontal = not horizontal
        elif op == 8:
            for i in range(0, len(s) - 5, 6):
                self._curve(*s[i:i + 6])
        elif op == 24:
            i = 0
            while len(s) - i >= 8:
                self._curve(*s[i:i + 6])
                i += 6
            self._line(s[i], s[i + 1])
        elif op == 25:
            i = 0
            while len(s) - i > 6:
                self._line(s[i], s[i + 1])
                i += 2
            self._curve(*s[i:i + 6])
        elif op in (26, 27):
            self._hh_vv(s, op == 27)
        elif op in (30, 31):
            self._hv(s, op == 31)
        elif op == 14:
            self._strip_width(False, 0)
            self.ended = True

    def _hh_vv(self, s: list[float], horizontal: bool) -> None:
        i, extra = 0, 0.0
        if len(s) % 4:
            extra, i = s[0], 1
        while len(s) - i >= 4:
            a, b, c, d = s[i:i + 4]
            if horizontal:
                self._curve(a, extra, b, c, d, 0)
            else:
                self._curve(extra, a, b, c, 0, d)
            extra = 0.0
            i += 4

    def _hv(self, s: list[float], horizontal: bool) -> None:
        i = 0
        while len(s) - i >= 4:
            last = len(s) - i == 5
            a, b, c, d = s[i:i + 4]
            f = s[i + 4] if last else 0.0
            if horizontal:
                self._curve(a, 0, b, c, f, d)
            else:
                self._curve(0, a, b, c, d, f)
            i += 5 if last else 4
            horizontal = not horizontal

    def _flex(self, op: int) -> None:
        s = self.stack
        if op == 35 and len(s) >= 12:
            self._curve(*s[0:6])
            self._curve(*s[6:12])
        elif op == 34 and len(s) >= 7:
            dx1, dx2, dy2, dx3, dx4, dx5, dx6 = s[:7]
            self._curve(dx1, 0, dx2, dy2, dx3, 0)
            self._curve(dx4, 0, dx5, -dy2, dx6, 0)
        elif op == 36 and len(s) >= 9:
            dx1, dy1, dx2, dy2, dx3, dx4, dx5, dy5, dx6 = s[:9]
            self._curve(dx1, dy1, dx2, dy2, dx3, 0)
            self._curve(dx4, 0, dx5, dy5, dx6, -(dy1 + dy2 + dy5))
        elif op == 37 and len(s) >= 11:
            dx = sum(s[0:10:2])
            dy = sum(s[1:10:2])
            self._curve(*s[0:6])
            if abs(dx) > abs(dy):
                self._curve(s[6], s[7], s[8], s[9], s[10], -dy)
            else:
                self._curve(s[6], s[7], s[8], s[9], -dx, s[10])
