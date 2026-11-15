"""Shapes, gradients, text and nested groups with document shortcuts.

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
    sky = doc % svg.LinearGradient.vertical("lightskyblue", "white")
    sun = doc.radial_gradient(svg.Stop(0, "gold"), svg.Stop(1, "orange"), cx=0.5, cy=0.5, r=0.5)

    doc.rect(0, 0, WIDTH, HEIGHT, fill=sky)
    doc.circle(260, 50, 30, fill=sun)
    with doc.group(id="house", stroke="saddlebrown", stroke_width=2, transform="translate(40 80)") as house:
        doc.rect(0, 40, 100, 80, fill="wheat")
        doc.polygon([(-10, 40), (50, 0), (110, 40)], fill="firebrick")
        doc.rect(40, 80, 20, 40, fill="sienna")
        with house.group(fill="lightblue"):
            doc.rect(12, 56, 16, 16)
            doc.rect(72, 56, 16, 16)
    doc += [
        svg.ellipse(230, 180, 60, 10, fill="seagreen", opacity=0.6),
        svg.line(0, 199, WIDTH, 199, stroke="darkgreen", stroke_width=2),
    ]
    title = doc.text("Home", x=WIDTH / 2, y=24, text_anchor="middle", font_family="sans-serif", font_size=18)
    title.span(" sweet home", font_style="italic")
    return doc


def main(out_dir: Path) -> Path:
    target = out_dir / "basic_shapes.svg"
    build().save(target)
    return target


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    print(main(folder))
