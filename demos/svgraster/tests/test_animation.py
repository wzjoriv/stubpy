"""SMIL timing and interpolation, document snapshots, frames and video output."""
from __future__ import annotations

import math
import shutil

import numpy as np
import pytest

import svgraster
from svgraster.animation import (
    FFmpegNotFoundError,
    Scheduler,
    Timing,
    bezier_ease,
    collect,
    find_ffmpeg,
    frame_times,
    interpolate,
    parse_clock,
    parse_value,
    snapshot,
    timeline,
)
from svgraster.animation._timing import simple_time
from svgraster.animation._values import format_value
from svgraster.dom.document import Document
from tests.conftest import svg

HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.mark.parametrize("text,seconds", [
    ("2s", 2.0), ("150ms", 0.15), ("1.5", 1.5), ("0.5min", 30.0), ("1h", 3600.0), ("01:30", 90.0),
    ("00:01:02.5", 62.5), ("indefinite", math.inf), ("bogus", None),
])
def test_clock_values(text, seconds):
    assert parse_clock(text) == seconds


def _timing(**attrs) -> Timing:
    doc = Document.parse(svg('<rect><animate id="a" attributeName="x" ' +
                             " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/></rect>"))
    return Timing.from_node(doc.ids["a"])


class TestTiming:
    def test_active_duration(self):
        assert _timing(dur="2s").active_duration() == 2
        assert _timing(dur="2s", repeatCount="2.5").active_duration() == 5
        assert _timing(dur="2s", repeatCount="indefinite", repeatDur="7s").active_duration() == 7
        assert _timing().active_duration() == math.inf

    def test_intervals_freeze_and_remove(self):
        frozen, removed = _timing(dur="1s", begin="1s; 5s", fill="freeze"), _timing(dur="1s", begin="1s")
        sched = Scheduler({})
        assert sched.interval_at(frozen, 0.5) is None
        assert sched.interval_at(frozen, 1.5) == (1.0, 2.0)
        assert sched.interval_at(frozen, 3.0) == (1.0, 2.0)
        assert sched.interval_at(frozen, 5.2) == (5.0, 6.0)
        assert sched.interval_at(removed, 3.0) is None

    def test_simple_time_repeats_and_freezes_at_end(self):
        t = _timing(dur="2s", repeatCount="2")
        assert simple_time(t, 0.0, 4.0, 3.0) == (1.0, 1, False)
        assert simple_time(t, 0.0, 4.0, 9.0) == (2.0, 1, True)

    def test_syncbase_and_end(self):
        doc = Document.parse(svg('<rect><animate id="a" attributeName="x" dur="2s" begin="1s"/>'
                                 '<animate id="b" attributeName="y" dur="1s" begin="a.end+0.5s" end="a.begin+3s"/>'
                                 '</rect>'))
        anims = collect(doc)
        sched = Scheduler({a.node.id: a.timing for a in anims})
        assert sched.first_begin(anims[1].timing) == 3.5
        assert sched.interval_end(anims[1].timing, 3.5) == 4.0

    def test_event_begins_never_start(self):
        assert Scheduler({}).interval_at(_timing(dur="1s", begin="click"), 10.0) is None


class TestValues:
    def test_parse_and_format(self):
        v = parse_value("10px 20.5 -3e1")
        assert v.numbers == (10.0, 20.5, -30.0) and format_value(v) == "10px 20.5 -30"
        assert parse_value("#ff0000", "fill").color == (1.0, 0.0, 0.0, 1.0)
        assert parse_value("url(#g)", "fill").color is None

    def test_calc_modes(self):
        vals = [parse_value(v) for v in ("0", "10", "30")]
        assert interpolate(vals, 0.25).numbers == (5.0,)
        assert interpolate(vals, 0.75).numbers == (20.0,)
        assert interpolate(vals, 0.4, "discrete").numbers == (10.0,)
        assert interpolate(vals, 0.5, "paced").numbers == (15.0,)
        assert interpolate(vals, 0.5, "linear", [0, 0.5, 1]).numbers == (10.0,)
        assert interpolate(vals, 1.0).numbers == (30.0,)

    def test_splines(self):
        assert bezier_ease((0, 0, 1, 1), 0.3) == pytest.approx(0.3, abs=1e-3)
        assert bezier_ease((0.5, 0, 0.5, 1), 0.25) < 0.25
        vals = [parse_value("0"), parse_value("100")]
        eased = interpolate(vals, 0.25, "spline", None, [(0.5, 0, 0.5, 1)]).numbers[0]
        assert 0 < eased < 25

    def test_incompatible_values_switch_halfway(self):
        vals = [parse_value("none", "fill"), parse_value("red", "fill")]
        assert interpolate(vals, 0.4).text == "none" and interpolate(vals, 0.6).text == "red"


MOVING = svg('<rect id="r" x="0" y="0" width="4" height="4" fill="red">'
             '<animate attributeName="x" from="0" to="16" dur="2s" fill="freeze"/>'
             '<animateColor attributeName="fill" values="red;blue" dur="2s" fill="freeze"/>'
             '<set attributeName="height" to="8" begin="1s"/></rect>', 20, 20)


class TestSnapshots:
    def test_attribute_and_property_animation(self):
        doc = Document.parse(MOVING)
        half = snapshot(doc, 1.0)
        rect = half.ids["r"]
        assert rect.attrs["x"] == "8" and rect.attrs["height"] == "8"
        assert rect.style["fill"] == "rgb(128, 0, 128)"
        assert doc.ids["r"].attrs["x"] == "0"
        assert snapshot(doc, 5.0).ids["r"].style["fill"] == "rgb(0, 0, 255)"

    def test_additive_accumulate_and_by(self):
        doc = Document.parse(svg('<rect id="r" x="10"><animate attributeName="x" by="5" dur="1s" '
                                 'repeatCount="3" accumulate="sum" fill="freeze"/></rect>'))
        assert snapshot(doc, 0.5).ids["r"].attrs["x"] == "12.5"
        assert snapshot(doc, 1.5).ids["r"].attrs["x"] == "17.5"
        assert snapshot(doc, 10).ids["r"].attrs["x"] == "25"

    def test_to_animation_starts_from_base(self):
        doc = Document.parse(svg('<rect id="r" width="10"><animate attributeName="width" to="20" dur="1s"/></rect>'))
        assert snapshot(doc, 0.5).ids["r"].attrs["width"] == "15"

    def test_animate_transform(self):
        doc = Document.parse(svg('<rect id="r" transform="translate(5)"><animateTransform attributeName="transform" '
                                 'type="rotate" from="0 10 10" to="90 10 10" dur="1s" additive="sum"/></rect>'))
        assert snapshot(doc, 0.5).ids["r"].attrs["transform"] == "translate(5) rotate(45 10 10)"

    def test_animate_motion_with_mpath(self):
        doc = Document.parse(svg('<path id="p" d="M0 0 H10 V10"/><rect id="r" width="1" height="1">'
                                 '<animateMotion dur="2s" rotate="auto"><mpath href="#p"/></animateMotion></rect>'))
        transform = snapshot(doc, 1.5).ids["r"].attrs["transform"]
        assert transform.startswith("translate(10 5") and "rotate(90" in transform

    def test_timeline(self):
        assert timeline(Document.parse(MOVING)) == 2.0
        assert timeline(Document.parse(svg(""))) == 0.0

    def test_render_at_times(self):
        start, middle = svgraster.render(MOVING, time=0), svgraster.render(MOVING, time=1)
        assert start[2, 1].tolist() == [255, 0, 0, 255] and start[2, 10, 3] == 0
        assert middle[2, 10, 3] == 255 and middle[6, 10, 3] == 255
        assert np.array_equal(svgraster.render(MOVING), start)


class TestFrames:
    def test_frame_times(self):
        assert frame_times(1.0, 4) == [0, 0.25, 0.5, 0.75]
        with pytest.raises(ValueError):
            frame_times(1.0, 0)

    def test_frames_and_frame_renderer(self):
        frames = list(svgraster.frames(MOVING, fps=2))
        assert [t for t, _ in frames] == [0, 0.5, 1.0, 1.5]
        render_at = svgraster.frame_renderer(MOVING, background="white")
        assert render_at(1.0).shape == (20, 20, 4) and render_at(0)[19, 19].tolist() == [255, 255, 255, 255]

    def test_png_sequence_and_npy(self, tmp_path):
        svgraster.render_animation(MOVING, tmp_path / "f_%03d.png", fps=2)
        assert sorted(p.name for p in tmp_path.glob("f_*.png")) == [f"f_{i:03d}.png" for i in range(4)]
        out = svgraster.render_animation(MOVING, tmp_path / "stack.npy", fps=4, duration=0.5)
        assert np.load(out).shape == (2, 20, 20, 4)

    def test_missing_ffmpeg_is_explained(self, tmp_path):
        with pytest.raises(FFmpegNotFoundError, match="PNG sequence"):
            find_ffmpeg(tmp_path / "no-ffmpeg-here")
        with pytest.raises(ValueError, match="unsupported"):
            svgraster.render_animation(MOVING, tmp_path / "x.avi")

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not on PATH")
    @pytest.mark.parametrize("suffix", [".mp4", ".gif"])
    def test_ffmpeg_video(self, tmp_path, suffix):
        out = svgraster.render_animation(MOVING, tmp_path / f"clip{suffix}", fps=5, width=21)
        assert out.exists() and out.stat().st_size > 100
