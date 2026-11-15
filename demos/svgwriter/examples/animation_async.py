"""SMIL animation, written concurrently with the async helpers.

Usage: python animation_async.py [OUTPUT_DIR]
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import svgwriter as svg
from svgwriter.io import write_many_async

SIZE = 200
FRAMES = 3


def spinner(speed: float) -> svg.Svg:
    doc = svg.Document(SIZE, SIZE)
    blade = svg.Rect(95, 20, 10, 80, rx=5, fill="steelblue")
    blade.append(svg.AnimateTransform.spin(100, 100, dur=speed))
    doc.add(blade)

    track = doc.define(svg.Path(svg.PathBuilder().circle(100, 100, 70)))
    dot = doc.add(svg.Circle(0, 0, 8, fill="tomato"))
    dot.append(svg.AnimateMotion(svg.MPath(track), dur=speed * 2, repeat_count=float("inf")))
    dot.append(svg.Animate(attribute_name="r", values=[6, 10, 6], dur=1, repeat_count=float("inf")))
    dot.append(svg.Set("visibility", "hidden", begin=speed * 4, fill=svg.AnimationFill.FREEZE))
    return doc.root


async def write_all(out_dir: Path) -> list[Path]:
    targets = {out_dir / f"spinner_{i}.svg": spinner(1.0 + i) for i in range(FRAMES)}
    await write_many_async(targets)
    return list(targets)


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="svgwriter-"))
    for path in asyncio.run(write_all(folder)):
        print(path)
