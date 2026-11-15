"""A procedural animation scene for ``python -m svgwriter animate``.

Usage:
    python -m svgwriter animate examples/orbit_scene.py -o orbit.gif --renderer skia
    python orbit_scene.py [OUTPUT_DIR]      writes the first frame as SVG
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import svgwriter as svg

SIZE = 160
CENTER = SIZE / 2
ORBIT = 50
FPS = 24
DURATION = 2.0
RENDERER = "skia"

_planet: svg.Circle | None = None


def build() -> svg.Document:
    global _planet
    doc = svg.Document(SIZE, SIZE)
    glow = doc.radial_gradient(svg.Stop(0, "gold"), svg.Stop(1, "orangered"))
    doc.rect(0, 0, SIZE, SIZE, fill="midnightblue")
    doc.circle(CENTER, CENTER, ORBIT, fill="none", stroke="slategray", stroke_dasharray=(3, 3))
    doc.circle(CENTER, CENTER, 18, fill=glow)
    _planet = doc.circle(CENTER + ORBIT, CENTER, 7, fill="deepskyblue")
    return doc


def update(doc: svg.Document, seconds: float) -> None:
    assert _planet is not None
    angle = 2 * math.pi * seconds / DURATION
    _planet.cx = CENTER + ORBIT * math.cos(angle)
    _planet.cy = CENTER + ORBIT * math.sin(angle)


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    target = folder / "orbit_frame0.svg"
    build().save(target)
    print(target)
