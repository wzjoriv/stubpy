"""TrueType ``glyf`` outlines: simple and composite glyphs as quadratic paths."""
from __future__ import annotations

import numpy as np

from .. import _backend
from ..parse.pathdata import Path
from ._reader import FontFormatError, Reader

ON_CURVE = 0x01
X_SHORT = 0x02
Y_SHORT = 0x04
REPEAT = 0x08
X_SAME = 0x10
Y_SAME = 0x20
ARGS_ARE_WORDS = 0x0001
ARGS_ARE_XY = 0x0002
HAVE_SCALE = 0x0008
MORE_COMPONENTS = 0x0020
HAVE_XY_SCALE = 0x0040
HAVE_2X2 = 0x0080
MAX_COMPOSITE_DEPTH = 8


def py_simple_glyph(data: bytes, offset: int) -> tuple[list[int], np.ndarray]:
    """Contour end indices and an ``(N, 3)`` int32 array of ``x, y, on_curve``."""
    r = Reader(data, offset)
    n_contours = r.i16()
    if n_contours < 0:
        raise FontFormatError("not a simple glyph")
    r.pos += 8
    ends = list(r.array("H", n_contours))
    n = ends[-1] + 1 if ends else 0
    skip = r.u16()
    r.pos += skip
    flags = []
    while len(flags) < n:
        f = r.u8()
        flags.append(f)
        if f & REPEAT:
            flags.extend([f] * r.u8())
    flags = flags[:n]
    out = np.zeros((n, 3), dtype=np.int32)
    for axis, short, same in ((0, X_SHORT, X_SAME), (1, Y_SHORT, Y_SAME)):
        value = 0
        for i, f in enumerate(flags):
            if f & short:
                d = r.u8()
                value += d if f & same else -d
            elif not f & same:
                value += r.i16()
            out[i, axis] = value
    out[:, 2] = [f & ON_CURVE for f in flags]
    return ends, out


def simple_glyph(data: bytes, offset: int) -> tuple[list[int], np.ndarray]:
    """:func:`py_simple_glyph` through the C API module when it is built."""
    native = _backend.native("glyf")
    if native is None:
        return py_simple_glyph(data, offset)
    ends, packed = native.simple_glyph(data, offset)
    return list(ends), np.frombuffer(packed, dtype=np.int32).reshape(-1, 3)


def contour_path(path: Path, pts: np.ndarray) -> None:
    """Append one closed quadratic contour (``x, y, on`` rows) to ``path``."""
    n = len(pts)
    if n == 0:
        return
    xy = pts[:, :2].astype(np.float64)
    on = pts[:, 2].astype(bool)
    if on[0]:
        start, order = xy[0], range(1, n)
    elif on[-1]:
        start, order = xy[-1], range(0, n - 1)
    else:
        start, order = (xy[0] + xy[-1]) / 2.0, range(0, n)
    path.move_to(float(start[0]), float(start[1]))
    pending = None
    for i in order:
        p = xy[i]
        if on[i]:
            if pending is None:
                path.line_to(float(p[0]), float(p[1]))
            else:
                path.quad_to(float(pending[0]), float(pending[1]), float(p[0]), float(p[1]))
            pending = None
        else:
            if pending is not None:
                mid = (pending + p) / 2.0
                path.quad_to(float(pending[0]), float(pending[1]), float(mid[0]), float(mid[1]))
            pending = p
    if pending is not None:
        path.quad_to(float(pending[0]), float(pending[1]), float(start[0]), float(start[1]))
    path.close()


class GlyfOutlines:
    """Decodes ``glyf`` entries located through ``loca``."""

    def __init__(self, data: bytes, glyf: tuple[int, int], loca: tuple[int, int], long_offsets: bool,
                 num_glyphs: int):
        self.data = data
        self.base = glyf[0]
        count = num_glyphs + 1
        if long_offsets:
            self.offsets = np.frombuffer(data, ">u4", count=min(count, loca[1] // 4), offset=loca[0]).astype(np.int64)
        else:
            short = np.frombuffer(data, ">u2", count=min(count, loca[1] // 2), offset=loca[0])
            self.offsets = short.astype(np.int64) * 2

    def points(self, gid: int, depth: int = 0) -> tuple[list[int], np.ndarray]:
        """Contour ends and ``x, y, on`` points for ``gid`` with composites resolved."""
        if gid < 0 or gid + 1 >= len(self.offsets) or depth > MAX_COMPOSITE_DEPTH:
            return [], np.zeros((0, 3), dtype=np.int32)
        start, end = int(self.offsets[gid]), int(self.offsets[gid + 1])
        if end <= start:
            return [], np.zeros((0, 3), dtype=np.int32)
        pos = self.base + start
        n_contours = Reader(self.data, pos).i16()
        if n_contours >= 0:
            return simple_glyph(self.data, pos)
        return self._composite(pos, depth)

    def _composite(self, pos: int, depth: int) -> tuple[list[int], np.ndarray]:
        r = Reader(self.data, pos + 10)
        ends: list[int] = []
        chunks: list[np.ndarray] = []
        total = 0
        while True:
            flags, child = r.u16(), r.u16()
            if flags & ARGS_ARE_WORDS:
                a1, a2 = (r.i16(), r.i16()) if flags & ARGS_ARE_XY else (r.u16(), r.u16())
            else:
                a1, a2 = (r.array("b", 2)) if flags & ARGS_ARE_XY else r.array("B", 2)
            a = d = 1.0
            b = c = 0.0
            if flags & HAVE_SCALE:
                a = d = r.f2dot14()
            elif flags & HAVE_XY_SCALE:
                a, d = r.f2dot14(), r.f2dot14()
            elif flags & HAVE_2X2:
                a, b, c, d = r.f2dot14(), r.f2dot14(), r.f2dot14(), r.f2dot14()
            cends, cpts = self.points(child, depth + 1)
            pts = cpts.astype(np.float64)
            if len(pts):
                xy = pts[:, :2] @ np.array([[a, b], [c, d]])
                if flags & ARGS_ARE_XY:
                    dx, dy = a1, a2
                else:
                    parent = np.concatenate(chunks)[a1, :2] if chunks and a1 < total else np.zeros(2)
                    child_pt = xy[a2] if a2 < len(xy) else np.zeros(2)
                    dx, dy = parent - child_pt
                pts[:, 0], pts[:, 1] = xy[:, 0] + dx, xy[:, 1] + dy
                chunks.append(np.rint(pts).astype(np.int32))
                ends.extend(e + total for e in cends)
                total += len(pts)
            if not flags & MORE_COMPONENTS:
                break
        if not chunks:
            return [], np.zeros((0, 3), dtype=np.int32)
        return ends, np.concatenate(chunks)

    def outline(self, gid: int) -> Path:
        """The glyph as a path in font units (y up)."""
        ends, pts = self.points(gid)
        path = Path()
        start = 0
        for end in ends:
            contour_path(path, pts[start:end + 1])
            start = end + 1
        return path
