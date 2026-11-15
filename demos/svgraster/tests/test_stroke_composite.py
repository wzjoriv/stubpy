"""Stroking and compositing: the nanobind layer against the numpy fallbacks."""
from __future__ import annotations

import numpy as np
import pytest

from svgraster import _backend
from svgraster.raster import composite as comp
from svgraster.raster.scanline import coverage
from svgraster.raster.stroke import (
    CAPS,
    JOINS,
    circle_polygon,
    py_dash_polyline,
    py_stroke_polyline,
    stroke_polylines,
)
from tests.conftest import native_module

ZIGZAG = np.array([[2.0, 2.0], [10.0, 12.0], [18.0, 3.0], [26.0, 14.0]])
TRIANGLE = np.array([[3.0, 3.0], [25.0, 5.0], [12.0, 18.0]])


@pytest.mark.parametrize("join", JOINS)
@pytest.mark.parametrize("cap", CAPS)
@pytest.mark.parametrize("closed, pts", [(False, ZIGZAG), (True, TRIANGLE), (False, ZIGZAG[:1])])
def test_stroke_native_matches_fallback(join, cap, closed, pts):
    mod = native_module("_composite")
    args = (3.0, JOINS[join], CAPS[cap], 4.0, 0.1)
    native = mod.stroke(pts, closed, args[0], join=args[1], cap=args[2], miter_limit=args[3], tolerance=args[4])
    fallback = py_stroke_polyline(pts, closed, *args)
    assert len(native) == len(fallback)
    for a, b in zip(native, fallback):
        np.testing.assert_allclose(a, b, atol=1e-9)


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("offset", [0.0, 2.5, -7.0])
def test_dash_native_matches_fallback(closed, offset):
    mod = native_module("_composite")
    native = mod.dash(TRIANGLE, closed, [4.0, 2.0, 1.0], offset)
    fallback = py_dash_polyline(TRIANGLE, closed, [4.0, 2.0, 1.0], offset)
    assert len(native) == len(fallback)
    for a, b in zip(native, fallback):
        np.testing.assert_allclose(a, b, atol=1e-9)


def test_stroke_polygons_are_positively_oriented():
    for poly in py_stroke_polyline(ZIGZAG, False, 4.0, JOINS["miter"], CAPS["square"]):
        x, y = poly[:, 0], poly[:, 1]
        assert np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y) >= 0


def test_stroke_area_of_straight_line():
    polys = stroke_polylines([(np.array([[2.0, 5.0], [18.0, 5.0]]), False)], 4.0, cap="butt")
    assert coverage(polys, 20, 10).sum() == pytest.approx(64.0, abs=1e-3)
    polys = stroke_polylines([(np.array([[2.0, 5.0], [18.0, 5.0]]), False)], 4.0, cap="square")
    assert coverage(polys, 24, 10).sum() == pytest.approx(80.0, abs=1e-3)


def test_miter_limit_switches_to_bevel():
    sharp = np.array([[0.0, 0.0], [20.0, 1.0], [0.0, 2.0]])
    miter = py_stroke_polyline(sharp, False, 2.0, JOINS["miter"], 0, miter_limit=100.0)
    bevel = py_stroke_polyline(sharp, False, 2.0, JOINS["miter"], 0, miter_limit=4.0)
    assert len(miter[-1]) == 4 and len(bevel[-1]) == 3


def test_dash_pattern_lengths():
    line = np.array([[0.0, 0.0], [20.0, 0.0]])
    dashes = py_dash_polyline(line, False, [5.0, 3.0])
    assert [round(float(d[-1, 0] - d[0, 0]), 6) for d in dashes] == [5.0, 5.0, 4.0]
    assert py_dash_polyline(line, False, [0.0, 0.0])[0].shape == (2, 2)


def test_stroke_dispatch_native_matches_pure():
    native_module("_composite")
    lines = [(ZIGZAG, False), (TRIANGLE, True)]
    a = stroke_polylines(lines, 2.5, "round", "round", dashes=[3, 1], dash_offset=1.0)
    with _backend.pure_python():
        b = stroke_polylines(lines, 2.5, "round", "round", dashes=[3, 1], dash_offset=1.0)
    np.testing.assert_allclose(coverage(a, 30, 20), coverage(b, 30, 20), atol=1e-5)


def test_circle_polygon_native():
    mod = native_module("_composite")
    np.testing.assert_allclose(mod.circle_polygon(3.0, 4.0, 5.0, 0.1), circle_polygon(3.0, 4.0, 5.0, 0.1))


@pytest.mark.parametrize("op", comp.PORTER_DUFF)
def test_porter_duff_native_matches_fallback(op, rgba, rgba2):
    mod = native_module("_composite")
    np.testing.assert_allclose(mod.porter_duff(rgba2, rgba, op), comp.py_porter_duff(rgba2, rgba, op), atol=1e-6)


def test_porter_duff_known_values():
    red = np.array([[[1.0, 0.0, 0.0, 1.0]]], dtype=np.float32)
    half_blue = np.array([[[0.0, 0.0, 0.5, 0.5]]], dtype=np.float32)
    assert comp.porter_duff(half_blue, red, "src_over")[0, 0].tolist() == [1.0, 0.0, 0.0, 1.0]
    assert comp.porter_duff(red, half_blue, "src_over")[0, 0].tolist() == pytest.approx([0.5, 0.0, 0.5, 1.0])
    assert comp.porter_duff(half_blue, red, "src_in")[0, 0].tolist() == pytest.approx([0.5, 0.0, 0.0, 0.5])
    assert comp.porter_duff(half_blue, red, "xor")[0, 0].tolist() == pytest.approx([0.5, 0.0, 0.0, 0.5])
    with pytest.raises(ValueError):
        comp.py_porter_duff(red, red, "bogus")


def test_paint_and_over_native_matches_fallback(rgba, rgba2, rng):
    mod = native_module("_composite")
    cov = rng.random(rgba.shape[:2]).astype(np.float32)
    for paint in ((0.2, 0.1, 0.3, 0.6), rgba2):
        a, b = rgba.copy(), rgba.copy()
        mod.paint_coverage(a, cov, paint)
        comp.py_paint_coverage(b, cov, paint)
        np.testing.assert_allclose(a, b, atol=1e-6)
    a, b = rgba.copy(), rgba.copy()
    mod.over(a, rgba2, opacity=0.4)
    comp.py_over(b, rgba2, 0.4)
    np.testing.assert_allclose(a, b, atol=1e-6)
    with pytest.raises(TypeError):
        mod.over(a, rgba2, 0.4)


def test_mask_and_conversions_native_matches_fallback(rgba):
    mod = native_module("_composite")
    for mode in (0, 1):
        np.testing.assert_allclose(mod.mask_values(rgba, mode), comp.py_mask_values(rgba, mode), atol=1e-6)
    for flag in (True, False):
        assert np.abs(mod.to_uint8(rgba, unpremultiply=flag).astype(int)
                      - comp.py_to_uint8(rgba, flag).astype(int)).max() <= 1
    u8 = comp.py_to_uint8(rgba)
    np.testing.assert_allclose(mod.to_float32(u8, premultiply=True), comp.py_to_float32(u8, True), atol=1e-6)


def test_uint8_round_trip(rgba):
    u8 = comp.to_uint8(rgba)
    back = comp.to_float32(u8)
    assert np.abs(back - np.clip(rgba, 0, 1)).max() < 0.01


def test_signatures():
    mod = native_module("_composite")
    assert mod.stroke.__doc__.startswith("stroke(points: numpy.ndarray, closed: bool, width: float, *,")
    assert "Overloaded function" in mod.paint_coverage.__doc__ or mod.paint_coverage.__doc__.count("paint_coverage(") == 2
    assert {m.name for m in mod.LineJoin} == {"MITER", "ROUND", "BEVEL"}
