"""Documents built with svgwriter render directly, and svgraster drives svgwriter's animation hook."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

import svgraster

WRITER_ROOT = Path(__file__).resolve().parents[2] / "svgwriter"
if WRITER_ROOT.is_dir() and str(WRITER_ROOT) not in sys.path:
    sys.path.insert(0, str(WRITER_ROOT))
svg = pytest.importorskip("svgwriter", reason="svgwriter is not importable from demos/svgwriter")


def _render(doc, **kwargs) -> np.ndarray:
    return svgraster.render(doc, dtype="float32", **kwargs)


def test_shapes_render_from_the_object():
    doc = svg.Document(40, 30)
    doc.add(svg.Rect(0, 0, 20, 30, fill="red"))
    doc.add(svg.Circle(30, 15, 8, fill="blue", stroke="black", stroke_width=2))
    img = _render(doc)
    assert img.shape == (30, 40, 4)
    np.testing.assert_allclose(img[15, 5], [1, 0, 0, 1])
    np.testing.assert_allclose(img[15, 30], [0, 0, 1, 1])
    assert img[15, 22, :3].max() < 0.1 and img[2, 38, 3] == 0


def test_gradients_and_filters():
    doc = svg.Document(60, 40)
    grad = doc.define(svg.LinearGradient.vertical("white", "black"))
    shadow = doc.define(svg.drop_shadow(4, 4, blur=1, color="black", opacity=1))
    doc.add(svg.Rect(0, 0, 60, 40, fill=grad))
    doc.add(svg.Rect(10, 10, 20, 15, fill="gold", filter=shadow))
    img = _render(doc)
    assert img[1, 50, 0] > img[38, 50, 0]
    np.testing.assert_allclose(img[15, 15, :3], [1, 0.843, 0], atol=0.01)
    assert img[27, 32, :3].max() < img[1, 50, :3].min()


def test_text_and_markers():
    doc = svg.Document(120, 40)
    arrow = doc.define(svg.Marker(svg.Path("M0 0 L6 3 L0 6 z", fill="green"), ref_x=3, ref_y=3, marker_width=6,
                                  marker_height=6, orient="auto", marker_units="userSpaceOnUse"))
    doc.add(svg.Line(5, 30, 100, 30, stroke="black", marker_end=arrow))
    doc.add(svg.Text("Hello", x=5, y=20, font_size=16, font_family="sans-serif", fill="navy"))
    img = _render(doc)
    assert img[5:22, 5:60, 3].max() > 0.9
    assert img[28:33, 99:104, 1].max() > 0.4


def test_animation_through_render_time():
    doc = svg.Document(40, 10)
    rect = svg.Rect(0, 0, 10, 10, fill="purple")
    rect.append(svg.Animate(attribute_name="x", from_=0, to=30, dur=2, fill="freeze"))
    doc.add(rect)
    assert _render(doc, time=0)[5, 5, 3] == 1 and _render(doc, time=0)[5, 35, 3] == 0
    assert _render(doc, time=2)[5, 35, 3] == 1 and _render(doc, time=2)[5, 5, 3] == 0


def test_svgwriter_animation_hook_uses_render_frame():
    from svgwriter.video.animation import iter_frames

    doc = svg.Document(20, 10)
    rect = svg.Rect(0, 0, 5, 10, fill="red")
    rect.append(svg.Animate(attribute_name="width", from_=5, to=20, dur=1, fill="freeze"))
    doc.add(rect)
    frames = list(iter_frames(doc, fps=4, duration=1.0, renderer="svgraster:render_frame"))
    assert len(frames) == 4
    widths = []
    for frame in frames:
        assert not frame.png and (frame.width, frame.height) == (20, 10)
        pixels = np.frombuffer(frame.data, np.uint8).reshape(frame.height, frame.width, 4)
        widths.append(int((pixels[5, :, 3] > 127).sum()))
    assert widths == sorted(widths) and widths[0] < widths[-1]
