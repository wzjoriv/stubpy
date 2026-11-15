"""An embedded SVG font, then a parse/re-serialize round trip.

Usage: python font_roundtrip.py [OUTPUT_DIR]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import svgwriter as svg

EM = 1000
ADVANCE = 600


def build() -> svg.Document:
    doc = svg.Document(400, 120)
    font = doc.define(svg.Font(svg.FontFace(font_family="Blocks", units_per_em=EM, ascent=800, descent=-200), horiz_adv_x=ADVANCE))
    font.add(svg.MissingGlyph(d="M50 0 h500 v700 h-500 z"))
    font.glyph("I", "M250 0 h100 v700 h-100 z")
    font.glyph("L", "M100 0 h400 v100 h-300 v600 h-100 z")
    font.glyph("T", "M250 0 h100 v600 h200 v100 h-500 v-100 h200 z")
    font.add(svg.HKern.pair("L", "T", 120))
    sheet = svg.StyleSheet().rule(".big", font_family="Blocks", font_size=64, fill="indigo")
    doc.root.insert(0, svg.StyleElement(sheet))
    doc.add(svg.Text("LIT", x=20, y=90, class_="big"))
    return doc


def main(out_dir: Path) -> tuple[Path, bool]:
    original = out_dir / "font.svg"
    build().save(original)
    reparsed = svg.Document.from_file(original)
    copy = out_dir / "font_copy.svg"
    reparsed.save(copy)
    return copy, original.read_text(encoding="utf-8") == copy.read_text(encoding="utf-8")


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    path, identical = main(folder)
    print(path, "identical" if identical else "DIFFERENT")
    sys.exit(0 if identical else 1)
