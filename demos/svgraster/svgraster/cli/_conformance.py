"""``svgraster conformance``: score renders against the W3C SVG 1.1 test suite's reference PNGs."""
from __future__ import annotations

import fnmatch
import gzip
import os
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..animation import collect, timeline
from ..dom.document import Document
from ..io.png import decode_png_rgba
from ..render import Renderer

SUITE_ENV = "SVGRASTER_SUITE"
OUT_OF_SCOPE_CHAPTERS = {"script": "scripting", "interact": "interactivity and events", "extend": "foreignObject",
                         "svgdom": "SVG DOM"}
OUT_OF_SCOPE_MARKERS = {b"<script": "scripting", b"foreignObject": "foreignObject"}
CHANNEL_TOLERANCE = 64
PASS_MISMATCH = 0.01
NEIGHBOURHOOD = 1
BACKGROUND = "white"


@dataclass
class Outcome:
    """One test's result."""

    name: str
    chapter: str
    status: str
    mismatch: float = 1.0
    seconds: float = 0.0
    note: str = ""


def default_suite() -> Path | None:
    """``SVGRASTER_SUITE``, ``./conformance/suite`` or the project's ``conformance/suite``."""
    candidates = [os.environ.get(SUITE_ENV), "conformance/suite", Path(__file__).resolve().parents[2]
                  / "conformance" / "suite"]
    for c in candidates:
        if c and (Path(c) / "svg").is_dir():
            return Path(c)
    return None


def _box_blur(img: np.ndarray) -> np.ndarray:
    padded = np.pad(img.astype(np.float32), ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = img.shape[:2]
    return sum(padded[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)) / 9.0


def mismatch(rendered: np.ndarray, reference: np.ndarray) -> float:
    """Fraction of pixels that, after a 3x3 box blur of both images (which forgives anti-aliasing
    differences on thin lines), differ by more than ``CHANNEL_TOLERANCE`` from every reference pixel
    within ``NEIGHBOURHOOD`` pixels."""
    h, w = reference.shape[:2]
    if rendered.shape[:2] != (h, w):
        return 1.0
    a = _box_blur(rendered[..., :3])
    b = _box_blur(reference[..., :3])
    bad = np.ones((h, w), dtype=bool)
    padded = np.pad(b, ((NEIGHBOURHOOD, NEIGHBOURHOOD), (NEIGHBOURHOOD, NEIGHBOURHOOD), (0, 0)), mode="edge")
    for dy in range(2 * NEIGHBOURHOOD + 1):
        for dx in range(2 * NEIGHBOURHOOD + 1):
            shifted = padded[dy:dy + h, dx:dx + w]
            bad &= np.abs(a - shifted).max(axis=-1) > CHANNEL_TOLERANCE
    return float(bad.mean())


def _scope(name: str, data: bytes) -> str | None:
    chapter = name.split("-", 1)[0]
    if chapter in OUT_OF_SCOPE_CHAPTERS:
        return OUT_OF_SCOPE_CHAPTERS[chapter]
    if "-dom-" in name:
        return "SVG DOM"
    for marker, reason in OUT_OF_SCOPE_MARKERS.items():
        if marker in data:
            return reason
    return None


def run_test(path: Path, reference: Path, renderer: Renderer) -> Outcome:
    """Render one test (animated tests at the end of their timeline) and compare it with its reference."""
    name = path.name.split(".")[0]
    chapter = name.split("-", 1)[0]
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    reason = _scope(name, data)
    if reason:
        return Outcome(name, chapter, "skipped", note=reason)
    if not reference.exists():
        return Outcome(name, chapter, "skipped", note="no reference PNG")
    start = time.perf_counter()
    try:
        ref = decode_png_rgba(reference.read_bytes())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            doc = Document.parse(path)
            end = timeline(doc) if collect(doc) else None
            img = renderer.render_document(doc, width=ref.shape[1], height=ref.shape[0], background=BACKGROUND,
                                           time=end)
    except Exception as exc:  # noqa: BLE001 - any failure is a test error
        return Outcome(name, chapter, "error", seconds=time.perf_counter() - start, note=f"{type(exc).__name__}: {exc}")
    flat = ref.astype(np.float32)
    alpha = flat[..., 3:4] / 255.0
    ref_rgb = (flat[..., :3] * alpha + 255.0 * (1 - alpha)).astype(np.uint8)
    frac = mismatch(img, ref_rgb)
    status = "pass" if frac <= PASS_MISMATCH else "fail"
    return Outcome(name, chapter, status, frac, time.perf_counter() - start)


def write_report(outcomes: list[Outcome], path: Path) -> None:
    """A Markdown report: overall score, per-chapter scores, excluded tests and every result."""
    scored = [o for o in outcomes if o.status != "skipped"]
    passed = sum(o.status == "pass" for o in scored)
    lines = ["# svgraster conformance (W3C SVG 1.1 SE test suite)", ""]
    pct = 100.0 * passed / len(scored) if scored else 0.0
    lines += [f"**Score: {passed}/{len(scored)} ({pct:.1f}%)** in scope; a test passes when at most "
              f"{PASS_MISMATCH:.0%} of pixels (after a 3x3 box blur of both images) differ by more than "
              f"{CHANNEL_TOLERANCE}/255 from every reference pixel within {NEIGHBOURHOOD} px. Animated tests are "
              "rendered at the end of their timeline.", "",
              "| Chapter | Passed | Total | Score |", "| --- | ---: | ---: | ---: |"]
    for chapter in sorted({o.chapter for o in scored}):
        group = [o for o in scored if o.chapter == chapter]
        ok = sum(o.status == "pass" for o in group)
        lines.append(f"| {chapter} | {ok} | {len(group)} | {100.0 * ok / len(group):.0f}% |")
    skipped = [o for o in outcomes if o.status == "skipped"]
    if skipped:
        lines += ["", "## Excluded (out of scope)", ""]
        reasons: dict[str, list[str]] = {}
        for o in skipped:
            reasons.setdefault(o.note, []).append(o.name)
        for reason, names in sorted(reasons.items()):
            lines.append(f"- **{reason}** ({len(names)}): {', '.join(names)}")
    lines += ["", "## Results", "", "| Test | Status | Mismatch | Time (s) | Note |",
              "| --- | --- | ---: | ---: | --- |"]
    for o in scored:
        note = o.note.replace("|", "/")[:120]
        lines.append(f"| {o.name} | {o.status} | {100 * o.mismatch:.2f}% | {o.seconds:.2f} | {note} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_parser(sub) -> None:
    """Register ``conformance``."""
    p = sub.add_parser("conformance", help="score renders against the W3C SVG 1.1 test suite",
                       description="Render each suite test and compare it with the reference PNG.")
    p.add_argument("--suite", help=f"suite folder with svg/ and png/ (default: ${SUITE_ENV} or ./conformance/suite)")
    p.add_argument("--filter", default="", metavar="PATTERN", help="glob or substring of test names to run")
    p.add_argument("--report", help="write a Markdown report here")
    p.add_argument("--antialias", type=int, default=8, help="sub-scanlines per pixel row (default 8)")
    p.add_argument("--failures", action="store_true", help="print failing tests")
    p.set_defaults(run=run)


def run(args, parser) -> int:
    """Run the suite (or a filtered part of it)."""
    suite = Path(args.suite) if args.suite else default_suite()
    if suite is None or not (suite / "svg").is_dir():
        print("svgraster: conformance suite not found; pass --suite or download it with "
              "'python scripts/dev.py svgraster fetch-suite'", file=sys.stderr)
        return 2
    tests = sorted(p for p in (suite / "svg").iterdir() if p.suffix in (".svg", ".svgz"))
    if args.filter:
        pattern = args.filter if any(c in args.filter for c in "*?[") else f"*{args.filter}*"
        tests = [t for t in tests if fnmatch.fnmatch(t.name, pattern)]
    renderer = Renderer(antialias=args.antialias)
    outcomes = []
    for path in tests:
        outcome = run_test(path, suite / "png" / (path.name.split(".")[0] + ".png"), renderer)
        outcomes.append(outcome)
        if args.failures and outcome.status in ("fail", "error"):
            print(f"{outcome.status:5} {outcome.name} {100 * outcome.mismatch:.1f}% {outcome.note}")
    scored = [o for o in outcomes if o.status != "skipped"]
    passed = sum(o.status == "pass" for o in scored)
    pct = 100.0 * passed / len(scored) if scored else 0.0
    print(f"conformance: {passed}/{len(scored)} passed ({pct:.1f}%), "
          f"{sum(o.status == 'error' for o in scored)} errors, {len(outcomes) - len(scored)} excluded")
    if args.report:
        write_report(outcomes, Path(args.report))
        print(f"wrote {args.report}")
    return 0
