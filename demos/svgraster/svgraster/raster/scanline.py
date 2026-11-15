"""Anti-aliased polygon coverage: the C scanline filler and its numpy twin.

Each pixel row is sampled by ``samples`` horizontal sub-scanlines; along each
one the covered spans are integrated exactly, so coverage is exact in x and
supersampled in y.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from .. import _backend

NONZERO = 0
EVENODD = 1
FILL_RULES = {"nonzero": NONZERO, "evenodd": EVENODD}
DEFAULT_SAMPLES = 16
MAX_SAMPLES = 256
SAMPLE_OFFSET = 0.5


def rule_code(rule: str | int) -> int:
    """Map ``"nonzero"``/``"evenodd"`` (or their codes) to the integer code."""
    if isinstance(rule, str):
        try:
            return FILL_RULES[rule]
        except KeyError:
            raise ValueError(f"unknown fill rule {rule!r}") from None
    if rule not in (NONZERO, EVENODD):
        raise ValueError(f"unknown fill rule {rule!r}")
    return int(rule)


def prepare_polygons(polygons: Iterable[np.ndarray]) -> list[np.ndarray]:
    """Contiguous float64 ``(N, 2)`` arrays, dropping ones with fewer than 2 points."""
    out = []
    for poly in polygons:
        arr = np.ascontiguousarray(poly, dtype=np.float64).reshape(-1, 2)
        if len(arr) >= 2:
            out.append(arr)
    return out


def _edges(polygons: Sequence[np.ndarray]) -> np.ndarray:
    if not polygons:
        return np.empty((0, 4))
    starts = np.concatenate(polygons)
    ends = np.concatenate([np.roll(p, -1, axis=0) for p in polygons])
    return np.column_stack([starts, ends])


def py_fill_polygons(out: np.ndarray, polygons: Sequence[np.ndarray], rule: int = NONZERO,
                     samples: int = DEFAULT_SAMPLES) -> None:
    """Accumulate coverage of ``polygons`` into the float32 ``out`` (numpy fallback)."""
    if not 1 <= samples <= MAX_SAMPLES:
        raise ValueError("samples out of range")
    height, width = out.shape
    edges = _edges(prepare_polygons(polygons))
    x0, y0, x1, y1 = edges.T if len(edges) else (np.empty(0),) * 4
    keep = y0 != y1
    x0, y0, x1, y1 = x0[keep], y0[keep], x1[keep], y1[keep]
    direction = np.where(y1 > y0, 1, -1)
    swap = y1 < y0
    x0, x1 = np.where(swap, x1, x0), np.where(swap, x0, x1)
    y0, y1 = np.where(swap, y1, y0), np.where(swap, y0, y1)
    if not len(x0):
        return
    dxdy = (x1 - x0) / (y1 - y0)
    k_total = height * samples
    ks = np.clip(np.ceil(y0 * samples - SAMPLE_OFFSET), 0, k_total).astype(np.int64)
    ke = np.clip(np.ceil(y1 * samples - SAMPLE_OFFSET), 0, k_total).astype(np.int64)
    counts = np.maximum(ke - ks, 0)
    total = int(counts.sum())
    if total == 0:
        return
    edge = np.repeat(np.arange(len(x0)), counts)
    first = np.repeat(np.cumsum(counts) - counts, counts)
    k = ks[edge] + (np.arange(total) - first)
    y = (k + SAMPLE_OFFSET) / samples
    x = x0[edge] + (y - y0[edge]) * dxdy[edge]
    order = np.lexsort((x, k))
    k, x, wdir = k[order], x[order], direction[edge][order]
    winding = np.cumsum(wdir)
    inside = (winding != 0) if rule == NONZERO else (winding % 2 != 0)
    span = inside[:-1] & (k[:-1] == k[1:])
    a = np.clip(x[:-1][span], 0.0, width)
    b = np.clip(x[1:][span], 0.0, width)
    rows = k[:-1][span] // samples
    valid = b > a
    a, b, rows = a[valid], b[valid], rows[valid]
    _accumulate_spans(out, rows, a, b, 1.0 / samples)


def _accumulate_spans(out: np.ndarray, rows: np.ndarray, a: np.ndarray, b: np.ndarray,
                      weight: float) -> None:
    height, width = out.shape
    steps = np.zeros((height, width + 1), dtype=np.float64)
    fracs = np.zeros((height, width + 1), dtype=np.float64)
    for ends, sign in ((a, -1.0), (b, 1.0)):
        cols = np.floor(ends).astype(np.int64)
        np.add.at(steps, (rows, cols), sign)
        np.add.at(fracs, (rows, cols), sign * (ends - cols))
    cover = -np.cumsum(steps, axis=1) + fracs
    out += (cover[:, :width] * weight).astype(np.float32)


def fill_polygons(out: np.ndarray, polygons: Iterable[np.ndarray], rule: str | int = "nonzero",
                  samples: int = DEFAULT_SAMPLES) -> np.ndarray:
    """Accumulate coverage into ``out`` using the C layer when built."""
    polys = prepare_polygons(polygons)
    code = rule_code(rule)
    native = _backend.native("scanline")
    if native is not None:
        native.fill_polygons(out, polys, code, samples)
        native.clamp_unit(out)
    else:
        py_fill_polygons(out, polys, code, samples)
        np.clip(out, 0.0, 1.0, out=out)
    return out


def coverage(polygons: Iterable[np.ndarray], width: int, height: int, rule: str | int = "nonzero",
             samples: int = DEFAULT_SAMPLES) -> np.ndarray:
    """A fresh ``(height, width)`` float32 coverage mask."""
    out = np.zeros((height, width), dtype=np.float32)
    return fill_polygons(out, polygons, rule, samples)


def polygon_area(points: np.ndarray) -> float:
    """Signed shoelace area (positive for counter-clockwise in y-up)."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    native = _backend.native("scanline")
    if native is not None:
        return native.polygon_area(np.ascontiguousarray(pts))
    x, y = pts[:, 0], pts[:, 1]
    return float(0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)))
