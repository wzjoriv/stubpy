"""Shapes, gradients, text and nested groups.

Usage: python basic_shapes.py [OUTPUT_DIR]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import svgwriter as svg

WIDTH, HEIGHT = 320, 200


def build() -> svg.Document:
    doc = svg.Document(WIDTH, HEIGHT)
    doc.title("Basic shapes")
    sky = doc.define(svg.LinearGradient.vertical("lightskyblue", "white"))
    sun = doc.define(svg.RadialGradient.from_colors(["gold", "orange"], cx=0.5, cy=0.5, r=0.5))

    doc.add(svg.Rect(0, 0, WIDTH, HEIGHT, fill=sky))
    doc.add(svg.Circle(260, 50, 30, fill=sun))
    with doc.group(id="house", stroke="saddlebrown", stroke_width=2, transform="translate(40 80)"):
        doc.add(svg.Rect(0, 40, 100, 80, fill="wheat"))
        doc.add(svg.Polygon([(-10, 40), (50, 0), (110, 40)], fill="firebrick"))
        doc.add(svg.Rect(40, 80, 20, 40, fill="sienna"))
        with doc.group(fill="lightblue"):
            doc.add(svg.Rect.square(16, x=12, y=56))
            doc.add(svg.Rect.square(16, x=72, y=56))
    doc.add(svg.Ellipse(230, 180, 60, 10, fill="seagreen", opacity=0.6))
    doc.add(svg.Line(0, 199, WIDTH, 199, stroke="darkgreen", stroke_width=2))
    doc.add(svg.Text("Home", svg.TSpan(" sweet home", font_style="italic"), x=WIDTH / 2, y=24, text_anchor="middle", font_family="sans-serif", font_size=18))
    return doc


def main(out_dir: Path) -> Path:
    target = out_dir / "basic_shapes.svg"
    build().save(target)
    return target


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    print(main(folder))
