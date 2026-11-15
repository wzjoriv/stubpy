"""The subcommands: render --time, animate, bench, fonts, backends and conformance."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from svgraster.cli import main
from svgraster.cli._conformance import default_suite, mismatch
from svgraster.io import read_png
from tests.test_animation import MOVING
from tests.test_fonts import TTF


@pytest.fixture
def anim_file(tmp_path) -> Path:
    path = tmp_path / "moving.svg"
    path.write_text(MOVING)
    return path


def test_render_subcommand_with_time(anim_file, tmp_path, capsys):
    out = tmp_path / "late.png"
    assert main(["render", str(anim_file), "-o", str(out), "--time", "1"]) == 0
    assert read_png(out)[2, 10, 3] == 255
    assert main([str(anim_file), "-o", str(tmp_path / "early.png")]) == 0
    assert read_png(tmp_path / "early.png")[2, 10, 3] == 0


def test_animate_png_sequence(anim_file, tmp_path, capsys):
    pattern = tmp_path / "frames" / "f_%02d.png"
    assert main(["animate", str(anim_file), "-o", str(pattern), "--fps", "2", "--background", "white"]) == 0
    assert len(list((tmp_path / "frames").glob("*.png"))) == 4
    assert "4 frames" in capsys.readouterr().out


def test_animate_reports_missing_ffmpeg(anim_file, tmp_path, capsys):
    code = main(["animate", str(anim_file), "-o", str(tmp_path / "x.mp4"), "--ffmpeg", str(tmp_path / "nope")])
    assert code == 1 and "ffmpeg was not found" in capsys.readouterr().err


def test_bench_json(capsys):
    assert main(["bench", "--size", "48", "--repeat", "1", "--json", "--compare"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert {r["scene"] for r in report["results"]} == {"shapes", "gradients", "text", "filters"}
    assert all(r["native"] > 0 and r["numpy"] > 0 for r in report["results"])


def test_backends_and_legacy_flag(capsys):
    assert main(["backends"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["--backends"]) == 0
    assert json.loads(capsys.readouterr().out) == first


@pytest.mark.skipif(TTF is None, reason="no TrueType test font")
def test_fonts_match_and_font_dir(tmp_path, capsys):
    (tmp_path / "copy.ttf").write_bytes(TTF.read_bytes())
    assert main(["fonts", "--font-dir", str(tmp_path), "--match", "serif", "--weight", "bold"]) == 0
    assert capsys.readouterr().out.strip()
    assert main(["fonts", "--dirs"]) == 0


def test_mismatch_metric_forgives_half_pixel_edges():
    ref = np.full((20, 20, 3), 255, np.uint8)
    ref[:, 10] = 0
    shifted = np.full((20, 20, 3), 255, np.uint8)
    shifted[:, 10:12] = 128
    assert mismatch(shifted, ref) == 0.0
    wrong = ref.copy()
    wrong[5:15, 2:8] = 0
    assert mismatch(wrong, ref) > 0.1


@pytest.mark.skipif(default_suite() is None, reason="W3C suite not downloaded")
def test_conformance_smoke(tmp_path, capsys):
    report = tmp_path / "report.md"
    assert main(["conformance", "--filter", "shapes-rect-0[12]*", "--report", str(report)]) == 0
    assert "2/2 passed" in capsys.readouterr().out
    assert "| shapes | 2 | 2 | 100% |" in report.read_text()
