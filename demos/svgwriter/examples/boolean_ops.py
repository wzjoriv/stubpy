"""Boolean path operations, text outlines and baked transforms.

Needs skia-python (``pip install 'svgwriter[ops]'``) for the boolean
operators; without it the script writes the plain composition instead.

Usage: python boolean_ops.py [OUTPUT_DIR]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import svgwriter as svg

SIZE = 240
CENTER = SIZE / 2
PETALS = 6
FONT = "Arial, Helvetica, sans-serif"


def petals() -> list[svg.Path]:
    petal = svg.Ellipse(CENTER, CENTER - 50, 22, 50)
    return [petal * svg.Transform.rotate(360 * i / PETALS, CENTER, CENTER) for i in range(PETALS)]


def build() -> svg.Document:
    doc = svg.Document(SIZE, SIZE)
    paint = doc % svg.LinearGradient.vertical("orchid", "indigo")
    doc.rect(0, 0, SIZE, SIZE, fill="ivory")
    flower = petals()
    if not svg.ops.available():
        doc += [p.update(fill=paint, opacity=0.8) for p in flower]
        doc.circle(CENTER, CENTER, 30, fill="gold")
        return doc
    blossom = flower[0].union(*flower[1:])
    blossom -= svg.Circle(CENTER, CENTER, 30)
    doc.path(blossom.d, fill=paint, stroke="indigo", stroke_width=2)
    badge = svg.Circle(CENTER, CENTER, 26, fill="gold") - svg.Text("A", x=CENTER, y=CENTER + 12, font_size=34, font_family=FONT, text_anchor="middle")
    doc += badge
    ring = svg.Circle(CENTER, CENTER, 110).stroked(4)
    ring.set("fill", "indigo")
    doc += ring
    return doc


def main(out_dir: Path) -> Path:
    target = out_dir / "boolean_ops.svg"
    build().save(target)
    return target


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    print(main(folder))
