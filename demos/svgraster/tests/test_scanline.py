"""Coverage rasterization: the C layer against the numpy fallback, areas and fill rules."""
from __future__ import annotations

import numpy as np
import pytest

from svgraster.raster import Rasterizer, make_rasterizer
from svgraster.raster.rasterizer import PyRasterizer
from svgraster.raster.scanline import coverage, polygon_area, prepare_polygons, py_fill_polygons, rule_code
from tests.conftest import native_module

SQUARE = np.array([[2.0, 2.0], [12.0, 2.0], [12.0, 12.0], [2.0, 12.0]])
INNER = np.array([[5.0, 5.0], [9.0, 5.0], [9.0, 9.0], [5.0, 9.0]])
STAR = np.array([[10.0, 1.0], [15.5, 18.0], [1.0, 7.5], [19.0, 7.5], [4.5, 18.0]])


def _py_coverage(polys, w, h, rule=0, samples=16):
    out = np.zeros((h, w), dtype=np.float32)
    py_fill_polygons(out, prepare_polygons(polys), rule, samples)
    return np.clip(out, 0, 1)


def _c_coverage(polys, w, h, rule=0, samples=16):
    mod = native_module("_scanline")
    out = np.zeros((h, w), dtype=np.float32)
    mod.fill_polygons(out, prepare_polygons(polys), rule, samples)
    mod.clamp_unit(out)
    return out


@pytest.mark.parametrize("rule", [0, 1])
@pytest.mark.parametrize("samples", [1, 4, 16])
@pytest.mark.parametrize("polys", [[SQUARE], [SQUARE, INNER], [STAR], [SQUARE * 1.37 + 0.31, STAR[::-1] * 0.9]])
def test_native_matches_fallback(polys, rule, samples):
    np.testing.assert_allclose(_c_coverage(polys, 24, 21, rule, samples),
                               _py_coverage(polys, 24, 21, rule, samples), atol=1e-5)


def test_native_matches_fallback_random(rng):
    polys = [rng.random((40, 2)) * 60 - 5 for _ in range(3)]
    for rule in (0, 1):
        np.testing.assert_allclose(_c_coverage(polys, 50, 50, rule, 8), _py_coverage(polys, 50, 50, rule, 8),
                                   atol=1e-5)


@pytest.mark.parametrize("samples", [4, 16, 64])
def test_coverage_sum_equals_area(samples):
    tri = np.array([[1.3, 2.1], [17.8, 4.4], [6.2, 15.9]])
    area = abs(polygon_area(tri))
    total = coverage([tri], 20, 20, samples=samples).sum(dtype=np.float64)
    assert total == pytest.approx(area, abs=20.0 / samples)


def test_axis_aligned_rect_is_exact():
    rect = np.array([[1.25, 2.0], [7.75, 2.0], [7.75, 6.0], [1.25, 6.0]])
    cov = coverage([rect], 10, 10)
    assert cov.sum() == pytest.approx(6.5 * 4.0, abs=1e-4)
    assert cov[3, 1] == pytest.approx(0.75) and cov[3, 7] == pytest.approx(0.75)
    assert cov[3, 4] == pytest.approx(1.0)


def test_fill_rules():
    nonzero = coverage([SQUARE, INNER], 14, 14, "nonzero")
    evenodd = coverage([SQUARE, INNER], 14, 14, "evenodd")
    assert nonzero[7, 7] == pytest.approx(1.0) and evenodd[7, 7] == pytest.approx(0.0)
    assert nonzero[3, 3] == evenodd[3, 3] == pytest.approx(1.0)
    opposite = coverage([SQUARE, INNER[::-1]], 14, 14, "nonzero")
    assert opposite[7, 7] == pytest.approx(0.0)


def test_star_center_depends_on_rule():
    assert coverage([STAR], 20, 20, "nonzero")[9, 10] == pytest.approx(1.0)
    assert coverage([STAR], 20, 20, "evenodd")[9, 10] == pytest.approx(0.0)


def test_offscreen_and_degenerate_polygons():
    assert coverage([SQUARE + 100], 10, 10).sum() == 0
    assert coverage([np.array([[1.0, 1.0], [5.0, 1.0]])], 10, 10).sum() == 0
    assert coverage([], 10, 10).shape == (10, 10)


def test_rule_code():
    assert rule_code("evenodd") == 1 and rule_code(0) == 0
    with pytest.raises(ValueError):
        rule_code("winding")


def test_polygon_area_sign():
    assert polygon_area(SQUARE) == pytest.approx(100.0)
    assert polygon_area(SQUARE[::-1]) == pytest.approx(-100.0)


class TestNativeApi:
    def test_text_signatures(self):
        mod = native_module("_scanline")
        assert mod.fill_polygons.__text_signature__ == "($module, out, polygons, rule=0, samples=4, /)"
        assert mod.polygon_area.__text_signature__ == "($module, points, /)"
        assert mod.clamp_unit.__text_signature__ is None
        assert mod.Rasterizer.__text_signature__ == "(width, height, samples=4)"
        assert mod.Rasterizer.from_shape.__text_signature__ == "($type, shape, samples=4)"

    def test_type_buffer_and_properties(self):
        mod = native_module("_scanline")
        r = mod.Rasterizer.from_shape((6, 8), samples=2)
        assert (r.width, r.height, r.samples) == (8, 6, 2)
        r.samples = 8
        with pytest.raises(ValueError):
            r.samples = 0
        with pytest.raises(AttributeError):
            r.width = 3
        r.fill([np.array([[0.0, 0.0], [8.0, 0.0], [8.0, 3.0], [0.0, 3.0]])])
        view = np.asarray(r)
        assert view.shape == (6, 8) and view.dtype == np.float32
        assert r.total() == pytest.approx(24.0)
        assert mod.coverage_sum(r) == pytest.approx(24.0)
        r.clear()
        assert r.total() == 0.0

    def test_bad_buffers(self):
        mod = native_module("_scanline")
        with pytest.raises(TypeError):
            mod.fill_polygons(np.zeros((4, 4), dtype=np.float64), [])
        with pytest.raises(TypeError):
            mod.fill_polygons(np.zeros((4, 4), dtype=np.float32), [np.zeros((3, 2), dtype=np.float32)])
        with pytest.raises(ValueError):
            mod.fill_polygons(np.zeros((4, 4), dtype=np.float32), [], 5)

    def test_python_subclass_forwards_kwargs(self):
        mod = native_module("_scanline")

        class Counting(mod.Rasterizer):
            def __init__(self, width, height, **kwargs):
                super().__init__(width, height, **kwargs)
                self.calls = 0

            def fill(self, polygons, rule=0):
                self.calls += 1
                super().fill(polygons, rule)

        r = Counting(10, 10, samples=3)
        r.fill([SQUARE])
        assert r.samples == 3 and r.calls == 1 and r.total() > 0


def test_public_rasterizer_subclass():
    r = Rasterizer(14, 14, rule="evenodd", samples=8)
    assert r.samples == 8 and r.rule == "evenodd"
    r.fill([SQUARE, INNER])
    arr = r.array()
    assert arr[7, 7] == pytest.approx(0.0) and arr[3, 3] == pytest.approx(1.0)
    r.fill([INNER], rule="nonzero")
    assert r.array()[7, 7] == pytest.approx(1.0)


def test_make_rasterizer_forwards_kwargs():
    r = make_rasterizer(12, 9, samples=2, rule="evenodd")
    assert (r.width, r.height, r.samples, r.rule) == (12, 9, 2, "evenodd")


def test_py_rasterizer_matches_native():
    mod = native_module("_scanline")
    native, fallback = mod.Rasterizer(24, 21, 8), PyRasterizer(24, 21, 8)
    for r in (native, fallback):
        r.fill(prepare_polygons([STAR, SQUARE]), 1)
    np.testing.assert_allclose(np.asarray(native), np.asarray(fallback.coverage()), atol=1e-5)
