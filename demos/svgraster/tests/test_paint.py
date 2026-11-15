"""Gradient and pattern paint servers: the Cython layers against the numpy fallbacks."""
from __future__ import annotations

import numpy as np
import pytest

from svgraster.dom import Matrix
from svgraster.raster import paint
from svgraster.raster.paint import GradientLUT, PyGradientLUT
from tests.conftest import native_module

OFFSETS = [0.0, 0.3, 0.3, 1.0]
COLORS = [(1, 0, 0, 1), (0, 1, 0, 0.5), (0, 0, 1, 1), (1, 1, 1, 0.25)]
INV = (Matrix.rotate(20) @ Matrix.scale(0.05, 0.08) @ Matrix.translate(-3, -2)).as_array()


@pytest.mark.parametrize("linear_rgb", [False, True])
@pytest.mark.parametrize("size", [2, 17, 1024])
def test_lut_native_matches_fallback(size, linear_rgb):
    mod = native_module("_paint")
    lut = mod.GradientLUT(np.array(OFFSETS), np.array(COLORS, dtype=np.float64), size=size, linear_rgb=linear_rgb)
    np.testing.assert_allclose(lut.table, paint.py_build_lut(OFFSETS, COLORS, size, linear_rgb), atol=2e-7)


@pytest.mark.parametrize("spread", [paint.PAD, paint.REFLECT, paint.REPEAT])
def test_linear_native_matches_fallback(spread):
    mod = native_module("_paint")
    table = paint.py_build_lut(OFFSETS, COLORS)
    a = np.zeros((31, 37, 4), dtype=np.float32)
    b = np.zeros_like(a)
    mod.linear_gradient(a, INV, 0.1, 0.2, 0.7, 0.4, table, spread)
    paint.py_linear_gradient(b, INV, 0.1, 0.2, 0.7, 0.4, table, spread)
    np.testing.assert_allclose(a, b, atol=1e-6)


@pytest.mark.parametrize("spread", [paint.PAD, paint.REFLECT, paint.REPEAT])
@pytest.mark.parametrize("focal", [(0.5, 0.5), (0.2, 0.6), (5.0, 5.0)])
def test_radial_native_matches_fallback(spread, focal):
    mod = native_module("_paint")
    table = paint.py_build_lut(OFFSETS, COLORS)
    a = np.zeros((31, 37, 4), dtype=np.float32)
    b = np.zeros_like(a)
    mod.radial_gradient(a, INV, 0.5, 0.5, 0.4, *focal, table, spread)
    paint.py_radial_gradient(b, INV, 0.5, 0.5, 0.4, *focal, table, spread)
    np.testing.assert_allclose(a, b, atol=1e-6)


def test_pattern_and_color_space_native_match_fallback(rgba):
    mod = native_module("_pattern")
    tile = rgba[:5, :7].copy()
    inv = (Matrix.scale(0.7) @ Matrix.rotate(15)).as_array()
    a = np.zeros((20, 30, 4), dtype=np.float32)
    b = np.zeros_like(a)
    mod.pattern_fill(a, tile, inv)
    paint.py_pattern_fill(b, tile, inv)
    np.testing.assert_array_equal(a, b)
    for to_linear in (True, False):
        x, y = rgba.copy(), rgba.copy()
        (mod.srgb_to_linear if to_linear else mod.linear_to_srgb)(x)
        paint.py_convert_space(y, to_linear)
        np.testing.assert_allclose(x, y, atol=1e-6)


def test_color_space_round_trip(rgba):
    img = rgba.copy()
    paint.convert_space(img, True)
    paint.convert_space(img, False)
    np.testing.assert_allclose(img, rgba, atol=1e-5)
    assert paint.srgb_to_linear_values(0.5) == pytest.approx(0.2140, abs=1e-4)


def test_lut_known_values():
    table = paint.build_lut([0.0, 1.0], [(1, 0, 0, 1), (0, 0, 1, 1)], size=3)
    np.testing.assert_allclose(table, [[1, 0, 0, 1], [0.5, 0, 0.5, 1], [0, 0, 1, 1]], atol=1e-7)
    premul = paint.build_lut([0.0, 1.0], [(1, 1, 1, 0), (1, 1, 1, 1)], size=3)
    np.testing.assert_allclose(premul[1], [0.5, 0.5, 0.5, 0.5])


def test_spread_methods_known_values():
    table = paint.build_lut([0.0, 1.0], [(0, 0, 0, 1), (1, 1, 1, 1)], size=1025)
    inv = Matrix.scale(1 / 10.0).as_array()
    out = np.zeros((1, 30, 4), dtype=np.float32)
    for spread, expected in ((paint.PAD, 1.0), (paint.REPEAT, 0.55), (paint.REFLECT, 0.45)):
        paint.linear_gradient(out, inv, 0, 0, 1, 0, table, spread)
        assert out[0, 15, 0] == pytest.approx(expected, abs=2e-3)


def test_radial_center_is_first_stop():
    table = paint.build_lut([0.0, 1.0], [(1, 0, 0, 1), (0, 0, 1, 1)])
    out = np.zeros((21, 21, 4), dtype=np.float32)
    inv = Matrix.translate(-10.5, -10.5).as_array()
    paint.radial_gradient(out, inv, 0, 0, 10, 0, 0, table)
    assert out[10, 10].tolist() == pytest.approx([1, 0, 0, 1], abs=1e-6)
    assert out[0, 0].tolist() == pytest.approx([0, 0, 1, 1], abs=1e-6)


def test_gradient_lut_subclass_forwards_kwargs():
    lut = GradientLUT([0.0, 1.0], [(1, 0, 0, 1), (0, 0, 1, 1)], size=16, linear_rgb=True)
    assert lut.size == 16 and lut.linear_rgb is True
    r, g, b, a = lut.sample(0.5)
    assert r == pytest.approx(0.713, abs=0.005) and a == 1.0
    assert lut.sample(1.5, paint.REFLECT) == lut.sample(0.5, paint.REFLECT)


def test_cython_types_and_signatures():
    mod = native_module("_paint")
    pat = native_module("_pattern")
    assert mod.linear_gradient.__doc__.startswith("linear_gradient(float[:, :, ::1] out")
    assert "GradientLUT" in type(mod.GradientLUT).__name__ or isinstance(mod.GradientLUT, type)
    lut = mod.GradientLUT(np.array([0.0, 1.0]), np.array([[0, 0, 0, 1], [1, 1, 1, 1]], dtype=np.float64), size=4)
    assert lut.size == 4 and not lut.linear_rgb
    with pytest.raises(AttributeError):
        lut.size = 5
    out = np.zeros((2, 3, 4), dtype=np.float32)
    lut.fill_linear(out, np.array([[1.0, 0, 0], [0, 1.0, 0]]), 0, 0, 3, 0)
    assert out[0, 2, 0] > out[0, 0, 0]
    tile = pat.PatternTile(np.ones((2, 3, 4), dtype=np.float32))
    assert (tile.width, tile.height) == (3, 2)
    with pytest.raises(ValueError):
        pat.PatternTile(np.ones((0, 3, 4), dtype=np.float32))


def test_py_gradient_lut_validation():
    with pytest.raises(ValueError):
        PyGradientLUT([], [])
    with pytest.raises(ValueError):
        PyGradientLUT([0.0], [(0, 0, 0, 1)], size=1)
