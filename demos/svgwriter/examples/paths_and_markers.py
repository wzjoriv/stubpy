"""Path data, arcs, markers, baked transforms and registered composite shapes.

Usage: python paths_and_markers.py [OUTPUT_DIR]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import svgwriter as svg
from svgwriter import builder

SIZE = 300


def build() -> svg.Document:
    doc = svg.Document(SIZE, SIZE)
    head = doc % builder.arrow_marker("crimson", 6)

    wave = svg.PathBuilder().move_to(20, 150)
    for _ in range(4):
        wave.quad_to(30, -40, 60, 0, relative=True).smooth_quad_to(60, 0, relative=True)
    doc.path(wave, fill="none", stroke="crimson", stroke_width=3, marker_end=head)

    pie = svg.PathBuilder().move_to(150, 150).line_to(150, 60).arc_to(90, 90, 0, False, True, 228, 195).close()
    slice_ = doc.path(pie, fill="gold", stroke="black", opacity=0.7)
    doc += slice_ * svg.Transform.rotate(180, 150, 150)

    with doc.group(stroke="navy", fill="none") as outlines:
        outlines += [
            builder.star(60, 60, 40, points=6),
            builder.gear(240, 60, 40, teeth=10),
            builder.arrow(40, 260, 260, 260, head=14),
            builder.dashed_line(20, 230, 280, 230),
        ]
    return doc


def main(out_dir: Path) -> list[Path]:
    doc = build()
    pretty = out_dir / "paths_pretty.svg"
    compact = out_dir / "paths_compact.svg"
    doc.save(pretty)
    doc.save(compact, pretty=False, compact_paths=True, precision=2)
    return [pretty, compact]


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    for path in main(folder):
        print(path, path.stat().st_size, "bytes")
