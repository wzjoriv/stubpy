"""Filter primitives: known pixels and pybind11 against the numpy fallbacks."""
from __future__ import annotations

import numpy as np
import pytest

from svgraster import _backend
from svgraster import filters as fx
from svgraster.filters import LightSpec, TransferSpec
from tests.conftest import native_module

BLEND_MODES = ["normal", "multiply", "screen", "darken", "lighten", "overlay", "color-dodge", "color-burn",
               "hard-light", "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity"]
COMPOSITE_OPS = ["over", "in", "out", "atop", "xor", "arithmetic", "lighter"]
MATRIX_KINDS = [("matrix", list(np.linspace(-0.5, 1.2, 20))), ("matrix", []), ("saturate", [0.3]),
                ("hueRotate", [73.0]), ("luminanceToAlpha", [])]
INV = np.array([[0.9, 0.2, 3.0], [-0.1, 1.1, 5.0]])
TRANSFERS = [TransferSpec("table", [0.0, 1.0, 0.2]), TransferSpec("discrete", [0.1, 0.9, 0.5, 0.3]),
             TransferSpec("linear", slope=0.5, intercept=0.25), TransferSpec("gamma", amplitude=2, exponent=0.5,
                                                                             offset=-0.1)]
LIGHTS = [LightSpec("distant", azimuth=30, elevation=40), LightSpec("point", position=(5.0, 6.0, 9.0)),
          LightSpec("spot", position=(1.0, 2.0, 20.0), points_at=(12.0, 9.0, 0.0), specular_exponent=3.0,
                    limiting_cone_angle=35.0),
          LightSpec("spot", position=(1.0, 2.0, 20.0), points_at=(12.0, 9.0, 0.0))]


def both(fn, *args, **kwargs):
    """Run ``fn`` with the native layer and with the fallback."""
    native_module("_filters")
    native = fn(*args, **kwargs)
    with _backend.pure_python():
        fallback = fn(*args, **kwargs)
    return native, fallback


def assert_equivalent(fn, *args, atol=1e-5, **kwargs):
    native, fallback = both(fn, *args, **kwargs)
    assert native.shape == fallback.shape and native.dtype == np.float32 == fallback.dtype
    np.testing.assert_allclose(native, fallback, atol=atol)
    return native


class TestEquivalence:
    @pytest.mark.parametrize("sx, sy", [(1.5, None), (0.0, 2.0), (2.5, 0.7), (0.0, 0.0)])
    def test_blur(self, rgba, sx, sy):
        assert_equivalent(fx.gaussian_blur, rgba, sx, sy)

    @pytest.mark.parametrize("dx, dy", [(2.4, -3.5), (-40, 0), (0.5, 0.49)])
    def test_offset(self, rgba, dx, dy):
        assert_equivalent(fx.offset, rgba, dx, dy)

    def test_flood(self):
        assert_equivalent(fx.flood, 4, 5, (0.1, 0.2, 0.3, 0.4))

    @pytest.mark.parametrize("mode", BLEND_MODES)
    def test_blend(self, rgba, rgba2, mode):
        assert_equivalent(fx.blend, rgba, rgba2, mode)

    @pytest.mark.parametrize("op", COMPOSITE_OPS)
    def test_composite(self, rgba, rgba2, op):
        assert_equivalent(fx.composite, rgba, rgba2, op, (0.5, 0.7, -0.2, 0.1))

    @pytest.mark.parametrize("kind, values", MATRIX_KINDS)
    def test_color_matrix(self, rgba, kind, values):
        assert_equivalent(fx.color_matrix, rgba, kind, values)

    def test_component_transfer(self, rgba):
        assert_equivalent(fx.component_transfer, rgba, TRANSFERS)
        assert_equivalent(fx.component_transfer, rgba, [None, TRANSFERS[0], None, TRANSFERS[3]])

    @pytest.mark.parametrize("op", ["erode", "dilate"])
    @pytest.mark.parametrize("rx, ry", [(1, 2), (0, 3), (0, 0)])
    def test_morphology(self, rgba, op, rx, ry):
        assert_equivalent(fx.morphology, rgba, rx, ry, op)

    @pytest.mark.parametrize("edge", ["duplicate", "wrap", "none"])
    @pytest.mark.parametrize("preserve", [False, True])
    def test_convolve(self, rgba, edge, preserve):
        kernel = np.array([[0, -1, 0.5], [-1, 5, -1], [0.25, -1, 0], [1, 0, 1]])
        assert_equivalent(fx.convolve_matrix, rgba, kernel, None, 0.1, (1, 2), edge, preserve)

    def test_tile_and_merge(self, rgba, rgba2):
        assert_equivalent(fx.tile, rgba, (3, 4, 5, 6))
        assert_equivalent(fx.tile, rgba, (-2, 1, 4, 30))
        assert_equivalent(fx.merge, [rgba, rgba2, rgba * 0.5])

    @pytest.mark.parametrize("stitch", [False, True])
    @pytest.mark.parametrize("fractal", [False, True])
    def test_turbulence(self, stitch, fractal):
        assert_equivalent(fx.turbulence, 19, 23, INV, (0.05, 0.11), 3, 7, stitch, fractal, (2.0, 3.0, 19.0, 23.0))

    @pytest.mark.parametrize("xc, yc", [("R", "G"), ("A", "B")])
    def test_displacement(self, rgba, rgba2, xc, yc):
        assert_equivalent(fx.displacement_map, rgba, rgba2, 7.5, xc, yc)

    @pytest.mark.parametrize("light", LIGHTS)
    def test_lighting(self, rgba, light):
        assert_equivalent(fx.diffuse_lighting, rgba, 2.5, 0.8, light, (1.0, 0.9, 0.5))
        assert_equivalent(fx.specular_lighting, rgba, 2.5, 1.2, 8.0, light, (0.6, 0.9, 1.0))


def _px(r, g, b, a=1.0):
    return np.array([[[r * a, g * a, b * a, a]]], dtype=np.float32)


class TestKnownPixels:
    def test_blur_preserves_mass_and_spreads(self):
        img = np.zeros((41, 41, 4), dtype=np.float32)
        img[20, 20] = 1.0
        out = fx.gaussian_blur(img, 2.0)
        assert out[..., 3].sum() == pytest.approx(1.0, abs=1e-5)
        assert out[20, 20, 3] == pytest.approx(1 / (2 * np.pi * 4), rel=0.02)
        assert out[20, 24, 3] < out[20, 22, 3] < out[20, 20, 3]

    def test_offset_moves_pixels(self):
        img = np.zeros((5, 5, 4), dtype=np.float32)
        img[1, 1] = 1.0
        out = fx.offset(img, 2, 1)
        assert out[2, 3, 3] == 1.0 and out[1, 1, 3] == 0.0

    def test_flood(self):
        assert fx.flood(2, 3, (0.25, 0.0, 0.0, 0.5))[1, 2].tolist() == [0.25, 0.0, 0.0, 0.5]

    @pytest.mark.parametrize("mode, expected", [
        ("normal", 0.8), ("multiply", 0.4), ("screen", 0.9), ("darken", 0.5), ("lighten", 0.8),
        ("difference", 0.3), ("exclusion", 0.5), ("overlay", 0.8), ("hard-light", 0.8),
    ])
    def test_blend_modes(self, mode, expected):
        out = fx.blend(_px(0.8, 0.8, 0.8), _px(0.5, 0.5, 0.5), mode)
        assert out[0, 0, 0] == pytest.approx(expected, abs=1e-5) and out[0, 0, 3] == pytest.approx(1.0)

    def test_non_separable_blend(self):
        out = fx.blend(_px(1, 0, 0), _px(0.5, 0.5, 0.5), "luminosity")
        assert out[0, 0, :3].tolist() == pytest.approx([0.3, 0.3, 0.3], abs=1e-5)
        out = fx.blend(_px(0.5, 0.5, 0.5), _px(1, 0, 0), "saturation")
        assert out[0, 0, :3].tolist() == pytest.approx([0.3, 0.3, 0.3], abs=1e-5)

    def test_composite_operators(self):
        a, b = _px(1, 0, 0, 0.5), _px(0, 0, 1, 1)
        assert fx.composite(a, b, "over")[0, 0].tolist() == pytest.approx([0.5, 0, 0.5, 1.0])
        assert fx.composite(a, b, "in")[0, 0].tolist() == pytest.approx([0.5, 0, 0, 0.5])
        assert fx.composite(a, b, "out")[0, 0].tolist() == pytest.approx([0, 0, 0, 0])
        assert fx.composite(b, a, "atop")[0, 0].tolist() == pytest.approx([0, 0, 0.5, 0.5])
        assert fx.composite(a, b, "arithmetic", (0, 0.5, 0.5, 0))[0, 0].tolist() == pytest.approx([0.25, 0, 0.5, 0.75])

    def test_color_matrix(self):
        assert fx.color_matrix(_px(1, 0, 0), "saturate", [0])[0, 0, 0] == pytest.approx(0.213, abs=1e-6)
        assert fx.color_matrix(_px(1, 1, 1), "luminanceToAlpha")[0, 0].tolist() == pytest.approx([0, 0, 0, 1.0],
                                                                                                    abs=1e-3)
        assert fx.color_matrix(_px(0.2, 0.4, 0.6), "hueRotate", [0])[0, 0].tolist() == pytest.approx(
            [0.2, 0.4, 0.6, 1.0], abs=1e-6)

    def test_component_transfer(self):
        out = fx.component_transfer(_px(1, 0.5, 0.25), [TransferSpec("linear", slope=0.5),
                                                        TransferSpec("table", [1.0, 0.0]),
                                                        TransferSpec("discrete", [0.2, 0.8]), None])
        assert out[0, 0].tolist() == pytest.approx([0.5, 0.5, 0.2, 1.0])

    def test_morphology(self):
        img = np.zeros((7, 7, 4), dtype=np.float32)
        img[3, 3] = 1.0
        assert fx.morphology(img, 1, 1, "dilate")[..., 3].sum() == 9
        assert fx.morphology(img, 1, 1, "erode")[..., 3].sum() == 0

    def test_convolve_identity_and_box(self, rgba):
        ident = np.zeros((3, 3))
        ident[1, 1] = 1
        np.testing.assert_allclose(fx.convolve_matrix(rgba, ident), np.minimum(rgba, 1), atol=1e-6)
        flat = np.full((5, 5, 4), 0.5, dtype=np.float32)
        assert fx.convolve_matrix(flat, np.ones((3, 3)))[2, 2].tolist() == pytest.approx([0.5] * 4)

    def test_tile(self):
        img = np.zeros((6, 6, 4), dtype=np.float32)
        img[0, 0] = 1.0
        out = fx.tile(img, (0, 0, 2, 2))
        assert out[..., 3].sum() == 9 and out[4, 2, 3] == 1.0

    def test_merge(self):
        out = fx.merge([_px(0, 0, 1), _px(1, 0, 0, 0.5)])
        assert out[0, 0].tolist() == pytest.approx([0.5, 0, 0.5, 1.0])

    def test_turbulence_properties(self):
        a = fx.turbulence(16, 16, INV, (0.1, 0.1), 2, seed=1)
        b = fx.turbulence(16, 16, INV, (0.1, 0.1), 2, seed=2)
        assert 0.0 <= a.min() and a.max() <= 1.0 and not np.allclose(a, b)
        np.testing.assert_array_equal(a, fx.turbulence(16, 16, INV, (0.1, 0.1), 2, seed=1))
        assert np.all(a[..., :3] <= a[..., 3:4] + 1e-6)

    def test_displacement_neutral_map_is_identity(self, rgba):
        neutral = np.full_like(rgba, 0.5)
        neutral[..., 3] = 1.0
        np.testing.assert_allclose(fx.displacement_map(rgba, neutral, 10.0, "R", "G"), rgba)

    def test_lighting_flat_surface(self):
        flat = np.ones((4, 4, 4), dtype=np.float32)
        overhead = LightSpec("distant", azimuth=0, elevation=90)
        out = fx.diffuse_lighting(flat, 1.0, 0.5, overhead, (1.0, 0.5, 0.0))
        assert out[2, 2].tolist() == pytest.approx([0.5, 0.25, 0.0, 1.0], abs=1e-6)
        spec = fx.specular_lighting(flat, 1.0, 0.7, 5.0, overhead)
        assert spec[2, 2].tolist() == pytest.approx([0.7, 0.7, 0.7, 0.7], abs=1e-6)
        cone = LightSpec("spot", position=(0, 0, 10), points_at=(100, 100, 0), limiting_cone_angle=5)
        assert fx.diffuse_lighting(flat, 1.0, 1.0, cone)[0, 0, :3].tolist() == [0.0, 0.0, 0.0]


class TestBindings:
    def test_enums_and_overloads(self):
        mod = native_module("_filters")
        assert mod.BlendMode.COLOR_DODGE.value == fx.BlendMode.COLOR_DODGE.value
        assert set(mod.CompositeOperator.__members__) == set(fx.CompositeOperator.__members__)
        img = np.zeros((3, 3, 4), dtype=np.float32)
        assert mod.gaussian_blur(img, 1.0).shape == mod.gaussian_blur(img, 1.0, 2.0).shape
        assert mod.flood(img, (0, 0, 0, 1)).shape == mod.flood(3, 3, (0, 0, 0, 1)).shape
        assert "Overloaded function" in mod.gaussian_blur.__doc__

    def test_transfer_function_constructors(self):
        mod = native_module("_filters")
        assert mod.TransferFunction().kind == mod.TransferType.IDENTITY
        table = mod.TransferFunction(mod.TransferType.TABLE, [0.0, 1.0, 0.0])
        assert table.values == [0.0, 1.0, 0.0] and table(0.5) == pytest.approx(1.0)
        assert mod.TransferFunction(2.0, 0.1)(0.5) == pytest.approx(1.1)
        gamma = mod.TransferFunction(1.0, 2.0, 0.0)
        assert gamma.kind == mod.TransferType.GAMMA and gamma(0.5) == pytest.approx(0.25)
        gamma.kind = mod.TransferType.LINEAR
        with pytest.raises(AttributeError):
            gamma.values = [1.0]

    def test_light_source_constructors(self):
        mod = native_module("_filters")
        assert mod.LightSource(10.0, 20.0).kind == mod.LightType.DISTANT
        point = mod.LightSource(1.0, 2.0, 3.0)
        assert point.kind == mod.LightType.POINT and list(point.position) == [1.0, 2.0, 3.0]
        spot = mod.LightSource(0, 0, 5, 1, 1, 0, limiting_cone_angle=30.0)
        assert spot.kind == mod.LightType.SPOT and spot.specular_exponent == 1.0
        spot.position = (4.0, 5.0, 6.0)
        assert list(spot.position) == [4.0, 5.0, 6.0]

    def test_keyword_defaults(self):
        mod = native_module("_filters")
        img = np.random.default_rng(0).random((4, 4, 4)).astype(np.float32)
        out = mod.convolve_matrix(img, kernel=np.ones((1, 1)), preserve_alpha=False)
        np.testing.assert_allclose(out[..., 3], img[..., 3], atol=1e-6)
        with pytest.raises(ValueError):
            mod.blend(img, img[:2])

    def test_blur_kwargs_wrapper(self, rgba):
        np.testing.assert_allclose(fx.blur(rgba, 1.0, sy=2.0), fx.gaussian_blur(rgba, 1.0, 2.0))
