"""Filter primitives: shadows, noise, lighting and color matrices.

Usage: python filter_effects.py [OUTPUT_DIR]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import svgwriter as svg
from svgwriter.elements import filters as fe

SIZE = 400
TILE = 160


def build() -> svg.Document:
    doc = svg.Document(SIZE, SIZE)
    shadow = doc.define(svg.drop_shadow(4, 4, 3, "black", 0.5))

    noise = fe.FeTurbulence(0.04, 4, seed=7, type=fe.TurbulenceType.FRACTAL_NOISE)
    paper = doc.define(svg.Filter(noise, fe.FeColorMatrix.saturate(0), x=0, y=0, width="100%", height="100%"))

    bump = fe.FeGaussianBlur(4, in_=fe.StandardInput.SOURCE_ALPHA)
    light = fe.FeSpecularLighting(
        fe.FePointLight(-50, -100, 200),
        in_=bump,
        surface_scale=5,
        specular_constant=0.8,
        specular_exponent=20,
        lighting_color="white",
    )
    clipped = fe.FeComposite(fe.CompositeOperator.IN, in_=light, in2=fe.StandardInput.SOURCE_ALPHA)
    shine = fe.FeComposite(fe.CompositeOperator.ARITHMETIC, in_=fe.StandardInput.SOURCE_GRAPHIC, in2=clipped, k1=0, k2=1, k3=1, k4=0)
    embossed = doc.define(svg.Filter(bump, light, clipped, shine))

    doc.add(svg.Rect(0, 0, SIZE, SIZE, filter=paper))
    doc.add(svg.Rect(20, 20, TILE, TILE, rx=16, fill="teal", filter=shadow))
    doc.add(svg.Circle(300, 100, 70, fill="darkorange", filter=embossed))
    grey = doc.define(svg.Filter(fe.FeColorMatrix.grayscale()))
    doc.add(svg.Text("grey", x=100, y=300, font_size=64, fill="purple", filter=grey))
    return doc


def main(out_dir: Path) -> Path:
    target = out_dir / "filter_effects.svg"
    build().save(target, doctype=True)
    return target


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    print(main(folder))
