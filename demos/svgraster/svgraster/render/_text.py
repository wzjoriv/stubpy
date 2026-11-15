"""Basic text: ``text``/``tspan`` laid out with the built-in stroke font."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from ..dom.node import Node
from ..dom.units import parse_length
from ._font import GRID_HEIGHT, glyph

CAP_HEIGHT_EM = 0.7
STROKE_EM = 0.1
BOLD_STROKE_EM = 0.15
BOLD_WEIGHTS = {"bold", "bolder", "600", "700", "800", "900"}
_SPACE_RE = re.compile(r"\s+")


@dataclass
class TextRun:
    """Glyph strokes sharing one style node."""

    node: Node
    strokes: list[np.ndarray] = field(default_factory=list)
    stroke_width: float = 1.0


def _first_length(node: Node, name: str, viewport, axis: str) -> float | None:
    raw = node.get(name)
    if raw is None or not raw.strip():
        return None
    return parse_length(raw.replace(",", " ").split()[0], node.units(viewport), axis)


def _chunks(node: Node):
    yield node, node.text, True
    for child in node.children:
        if child.tag in ("tspan", "a") and child.style.get("display") != "none":
            yield from _chunks(child)
        yield node, child.tail, False


def layout(node: Node, viewport: tuple[float, float]) -> list[TextRun]:
    """Lay out a ``text`` element into styled stroke runs in user space."""
    x = _first_length(node, "x", viewport, "x") or 0.0
    y = _first_length(node, "y", viewport, "y") or 0.0
    runs: list[TextRun] = []
    pending_space = False
    started = False
    for owner, raw, opens in _chunks(node):
        if opens and owner is not node:
            nx = _first_length(owner, "x", viewport, "x")
            ny = _first_length(owner, "y", viewport, "y")
            x = nx if nx is not None else x
            y = ny if ny is not None else y
            x += _first_length(owner, "dx", viewport, "x") or 0.0
            y += _first_length(owner, "dy", viewport, "y") or 0.0
        if not raw:
            continue
        text = _SPACE_RE.sub(" ", raw)
        if text.startswith(" "):
            pending_space = started
            text = text.lstrip()
        trailing = text.endswith(" ")
        text = text.rstrip()
        if not text:
            pending_space = pending_space or (started and trailing)
            continue
        if pending_space:
            text = " " + text
        size = owner.font_size
        unit = size * CAP_HEIGHT_EM / GRID_HEIGHT
        weight = owner.style.get("font-weight", "normal")
        run = TextRun(owner, stroke_width=size * (BOLD_STROKE_EM if weight in BOLD_WEIGHTS else STROKE_EM))
        for ch in text:
            strokes, advance = glyph(ch)
            for s in strokes:
                run.strokes.append(s * unit + (x, y))
            x += advance * unit
        runs.append(run)
        started = True
        pending_space = trailing
    anchor = node.style.get("text-anchor", "start")
    if anchor in ("middle", "end") and runs:
        start = _first_length(node, "x", viewport, "x") or 0.0
        shift = (x - start) / (2.0 if anchor == "middle" else 1.0)
        for run in runs:
            run.strokes = [s - (shift, 0.0) for s in run.strokes]
    return runs


def text_bounds(node: Node, viewport: tuple[float, float]) -> tuple[float, float, float, float] | None:
    """Bounds of the laid-out glyph strokes including stroke width."""
    pts, pad = [], 0.0
    for run in layout(node, viewport):
        pts.extend(run.strokes)
        pad = max(pad, run.stroke_width / 2.0)
    if not pts:
        return None
    allp = np.concatenate(pts)
    return (float(allp[:, 0].min() - pad), float(allp[:, 1].min() - pad),
            float(allp[:, 0].max() + pad), float(allp[:, 1].max() + pad))
