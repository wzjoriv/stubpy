"""``svgraster bench``: time built-in scenes (or given files) with the native layers and the fallbacks."""
from __future__ import annotations

import json
import statistics
import sys
import time

from .._backend import backend_info
from ..dom.document import Document
from ..render import Renderer

NS = 'xmlns="http://www.w3.org/2000/svg"'
SCENES = {
    "shapes": f'<svg {NS} viewBox="0 0 100 100">' + "".join(
        f'<circle cx="{(i * 37) % 100}" cy="{(i * 53) % 100}" r="{3 + i % 9}" fill="hsl({i * 13 % 360},70%,50%)" '
        f'stroke="black" stroke-width="0.5" opacity="0.8"/>' for i in range(200)) + "</svg>",
    "gradients": f'<svg {NS} viewBox="0 0 100 100"><defs><linearGradient id="a" x2="1" y2="1">'
                 '<stop offset="0" stop-color="navy"/><stop offset="1" stop-color="gold"/></linearGradient>'
                 '<radialGradient id="b" fx="0.3"><stop offset="0" stop-color="white"/>'
                 '<stop offset="1" stop-color="crimson" stop-opacity="0.2"/></radialGradient></defs>'
                 '<rect width="100" height="100" fill="url(#a)"/><circle cx="50" cy="50" r="40" fill="url(#b)"/></svg>',
    "text": f'<svg {NS} viewBox="0 0 200 100">' + "".join(
        f'<text x="4" y="{10 + 9 * i}" font-family="serif" font-size="8">The quick brown fox jumps over the lazy '
        f'dog {i}</text>' for i in range(10)) + "</svg>",
    "filters": f'<svg {NS} viewBox="0 0 100 100"><filter id="f"><feGaussianBlur stdDeviation="2" result="b"/>'
               '<feOffset dx="2.5" dy="1.5"/><feSpecularLighting surfaceScale="3" specularExponent="10" result="s">'
               '<fePointLight x="20" y="20" z="30"/></feSpecularLighting><feComposite in="s" in2="SourceAlpha" '
               'operator="in"/></filter><g filter="url(#f)"><rect x="15" y="15" width="70" height="70" rx="10" '
               'fill="teal"/></g></svg>',
}


def add_parser(sub) -> None:
    """Register ``bench``."""
    p = sub.add_parser("bench", help="time rendering of built-in scenes or SVG files")
    p.add_argument("files", nargs="*", help="SVG files to time instead of the built-in scenes")
    p.add_argument("--size", type=int, default=512, help="output width in pixels (default 512)")
    p.add_argument("--repeat", type=int, default=3, help="timed runs per scene (default 3)")
    p.add_argument("--threads", type=int, help="OpenMP threads for the native layers")
    p.add_argument("--compare", action="store_true", help="also time the numpy fallbacks")
    p.add_argument("--json", action="store_true", help="print results as JSON")
    p.set_defaults(run=run)


def _time(renderer: Renderer, doc: Document, size: int, repeat: int) -> float:
    renderer.render_document(doc, width=size)
    runs = []
    for _ in range(max(1, repeat)):
        start = time.perf_counter()
        renderer.render_document(doc, width=size)
        runs.append(time.perf_counter() - start)
    return statistics.median(runs)


def run(args, parser) -> int:
    """Time each scene and print a table."""
    sources = {f: f for f in args.files} if args.files else SCENES
    modes = [("native", True)] + ([("numpy", False)] if args.compare else [])
    results = []
    for name, source in sources.items():
        try:
            doc = Document.parse(source)
        except (OSError, ValueError) as exc:
            print(f"svgraster: {name}: {exc}", file=sys.stderr)
            return 1
        row = {"scene": name}
        for label, native in modes:
            renderer = Renderer(threads=args.threads, native=native)
            row[label] = _time(renderer, doc, args.size, args.repeat) * 1000.0
        results.append(row)
    if args.json:
        print(json.dumps({"size": args.size, "results": results,
                          "openmp": {k: v["openmp"] for k, v in backend_info().items()}}, indent=2))
        return 0
    header = f"{'scene':<12}" + "".join(f"{label + ' ms':>14}" for label, _ in modes)
    print(header)
    for row in results:
        print(f"{row['scene']:<12}" + "".join(f"{row[label]:>14.1f}" for label, _ in modes))
    return 0
