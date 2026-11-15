"""The command line, PNG/PPM/npy output and the numba helpers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from svgraster import _jit
from svgraster.__main__ import main
from svgraster.io import decode_png, encode_png, read_png, read_ppm, save
from tests.conftest import svg

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DOC = svg('<rect x="2" y="2" width="8" height="6" fill="red"/><circle cx="14" cy="14" r="4" fill="blue"/>')


@pytest.fixture
def svg_file(tmp_path) -> Path:
    path = tmp_path / "drawing.svg"
    path.write_text(DOC)
    return path


def test_png_round_trip(rgba):
    u8 = (rgba * 255).astype(np.uint8)
    np.testing.assert_array_equal(decode_png(encode_png(u8)), u8)
    np.testing.assert_array_equal(decode_png(encode_png(u8[..., :3])), u8[..., :3])
    with pytest.raises(ValueError):
        encode_png(u8[..., 0])


def test_cli_writes_png(svg_file, tmp_path, capsys):
    out = tmp_path / "out.png"
    assert main([str(svg_file), "-o", str(out), "--antialias", "4"]) == 0
    img = read_png(out)
    assert img.shape == (20, 20, 4) and img[5, 5].tolist() == [255, 0, 0, 255]
    assert "wrote" in capsys.readouterr().out


def test_cli_default_output_and_ppm(svg_file, tmp_path):
    assert main([str(svg_file)]) == 0
    assert svg_file.with_suffix(".png").exists()
    out = tmp_path / "out.ppm"
    assert main([str(svg_file), "-o", str(out), "--background", "black"]) == 0
    rgb = read_ppm(out)
    assert rgb.shape == (20, 20, 3) and rgb[5, 5].tolist() == [255, 0, 0] and rgb[0, 0].tolist() == [0, 0, 0]


def test_cli_npy_float_and_size(svg_file, tmp_path):
    out = tmp_path / "out.npy"
    assert main([str(svg_file), "-o", str(out), "--float", "--width", "40", "--pure"]) == 0
    arr = np.load(out)
    assert arr.shape == (40, 40, 4) and arr.dtype == np.float32


def test_cli_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.svg"), "-o", str(tmp_path / "x.png")]) == 1
    with pytest.raises(SystemExit):
        main([str(tmp_path / "a.svg"), "-o", str(tmp_path / "x.gif")])
    with pytest.raises(SystemExit):
        main([])


def test_cli_backends_report(capsys):
    assert main(["--backends"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {"scanline", "glyf", "paint", "pattern", "codec", "filters", "composite", "jit"}


def test_module_entry_point(svg_file, tmp_path):
    out = tmp_path / "cli.png"
    env = dict(os.environ, PYTHONPATH=str(PACKAGE_ROOT))
    result = subprocess.run([sys.executable, "-m", "svgraster", str(svg_file), "-o", str(out)],
                            capture_output=True, text=True, env=env, cwd=tmp_path, timeout=300)
    assert result.returncode == 0, result.stderr
    assert read_png(out).shape == (20, 20, 4)


def test_save_rejects_unknown_extension(tmp_path):
    with pytest.raises(ValueError):
        save(np.zeros((2, 2, 4), dtype=np.uint8), tmp_path / "x.bmp")


def test_jit_matches_numpy(rgba):
    big = np.repeat(np.repeat(rgba, 3, axis=0), 3, axis=1)
    np.testing.assert_allclose(_jit.downscale(big, 3), _jit.py_downscale(big, 3), atol=1e-6)
    np.testing.assert_allclose(_jit.downscale(big, 3), rgba, atol=1e-6)
    np.testing.assert_allclose(_jit.unpremultiply(rgba), _jit.py_unpremultiply(rgba), atol=1e-6)
    assert _jit.downscale(rgba, 1) is rgba


def test_jit_reports_numba():
    pytest.importorskip("numba")
    assert _jit.HAVE_NUMBA and hasattr(_jit._downscale_kernel, "py_func")
