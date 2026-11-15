"""Sub-pixel offset, bilinear sampling, spec edge kernels, resampling and the new filter inputs."""
from __future__ import annotations

import base64

import numpy as np
import pytest

from svgraster import filters as fx
from svgraster.filters._basic import py_offset
from svgraster.filters._enums import Channel, ResampleFilter
from svgraster.filters._lighting import PyLightSource, py_diffuse_lighting, surface_normals
from svgraster.filters._spatial import py_displacement_map
from svgraster.raster.sample import py_sample_image, sample_image
from tests.conftest import native_module, render_float, svg


class TestFallbacks:
    def test_half_pixel_offset_averages(self):
        img = np.zeros((1, 4, 4), np.float32)
        img[0, 1] = 1.0
        out = py_offset(img, 0.5, 0.0)
        np.testing.assert_allclose(out[0, :, 3], [0, 0.5, 0.5, 0])

    def test_whole_pixel_offset_unchanged(self, rgba):
        out = py_offset(rgba, 2.0, -1.0)
        np.testing.assert_allclose(out[:-1, 2:], rgba[1:, :-2], atol=1e-6)

    def test_displacement_interpolates(self):
        img = np.zeros((1, 3, 4), np.float32)
        img[0, 2] = 1.0
        disp = np.zeros((1, 3, 4), np.float32)
        disp[..., 0] = 0.75
        disp[..., 1] = 0.5
        disp[..., 3] = 1.0
        out = py_displacement_map(img, disp, 2.0, Channel.R, Channel.G)
        assert out[0, 1, 3] == pytest.approx(0.5)

    def test_spec_edge_kernel_corner(self):
        a = np.zeros((3, 3))
        a[0, 1] = 1.0
        nx, ny, nz = surface_normals(a, 1.0)
        raw_x = -(2.0 / 3.0) * (-2 * a[0, 0] + 2 * a[0, 1] - a[1, 0] + a[1, 1])
        assert nx[0, 0] * np.sqrt(raw_x ** 2 + ny[0, 0] ** 2 / nz[0, 0] ** 2 + 1) == pytest.approx(raw_x, rel=1e-3)
        flat = py_diffuse_lighting(np.zeros((4, 4, 4), np.float32), 1.0, 1.0, PyLightSource(0.0, 90.0))
        np.testing.assert_allclose(flat[..., :3], 1.0)

    def test_resample_identity_and_upscale(self, rgba):
        np.testing.assert_allclose(fx.py_resample(rgba, *rgba.shape[:2]), rgba, atol=1e-6)
        up = fx.py_resample(rgba, 34, 46, ResampleFilter.NEAREST)
        np.testing.assert_array_equal(up[::2, ::2], rgba)

    def test_bilinear_pattern_sampling(self):
        tile = np.zeros((1, 2, 4), np.float32)
        tile[0, 1] = 1.0
        out = np.zeros((1, 4, 4), np.float32)
        py_sample_image(out, tile, np.array([[0.5, 0, 0], [0, 1, 0]]), bilinear=True, repeat=True)
        assert 0 < out[0, 1, 3] < 1


class TestNativeMatchesFallback:
    @pytest.fixture(autouse=True)
    def _native(self):
        self.mod = native_module("_filters")

    @pytest.mark.parametrize("dx,dy", [(0.5, 0.0), (1.25, -2.75), (-0.3, 0.6), (3.0, 1.0)])
    def test_offset(self, rgba, dx, dy):
        np.testing.assert_allclose(self.mod.offset(rgba, dx, dy), py_offset(rgba, dx, dy), atol=1e-5)
        np.testing.assert_allclose(self.mod.offset(rgba, (dx, dy)), self.mod.offset(rgba, dx, dy))

    def test_displacement(self, rgba, rgba2):
        native = self.mod.displacement_map(rgba, rgba2, 7.3, self.mod.Channel.R, self.mod.Channel.B)
        np.testing.assert_allclose(native, py_displacement_map(rgba, rgba2, 7.3, Channel.R, Channel.B), atol=1e-5)

    @pytest.mark.parametrize("light", [PyLightSource(30.0, 50.0), PyLightSource(5.0, 4.0, 9.0)])
    def test_lighting_edges(self, rgba, light):
        args = (light.azimuth, light.elevation) if light.kind == 0 else light.position
        native = self.mod.diffuse_lighting(rgba, 3.0, 1.2, self.mod.LightSource(*args))
        np.testing.assert_allclose(native, py_diffuse_lighting(rgba, 3.0, 1.2, light), atol=1e-5)

    @pytest.mark.parametrize("size", [(9, 5), (40, 31), (17, 23)])
    def test_resample(self, rgba, size):
        native = self.mod.resample(rgba, *size, filter=self.mod.ResampleFilter.BILINEAR)
        np.testing.assert_allclose(native, fx.py_resample(rgba, *size), atol=1e-5)
        nearest = self.mod.resample(rgba, *size, filter=self.mod.ResampleFilter.NEAREST)
        np.testing.assert_allclose(nearest, fx.py_resample(rgba, *size, ResampleFilter.NEAREST))

    def test_cython_sampling(self, rgba):
        native_module("_pattern")
        inv = np.array([[0.7, 0.2, -1.3], [-0.1, 0.9, 2.2]])
        for bilinear in (True, False):
            for repeat in (True, False):
                a = np.zeros((19, 21, 4), np.float32)
                b = np.zeros_like(a)
                sample_image(a, rgba, inv, bilinear=bilinear, repeat=repeat)
                py_sample_image(b, rgba, inv, bilinear, repeat)
                np.testing.assert_allclose(a, b, atol=1e-5)


RED_RECT = '<rect x="5" y="5" width="10" height="10" fill="red"/>'


class TestFilterInputs:
    def test_subpixel_offset_in_document(self):
        img = render_float(svg('<filter id="f"><feOffset dx="0.5"/></filter>'
                               '<rect x="5" y="5" width="10" height="10" fill="blue" filter="url(#f)"/>'),
                           antialias=4)
        assert img[10, 5, 3] == pytest.approx(0.5, abs=0.02) and img[10, 15, 3] == pytest.approx(0.5, abs=0.02)

    def test_fill_paint(self):
        img = render_float(svg('<filter id="f" x="0" y="0" width="1" height="1"><feFlood flood-opacity="0"/>'
                               '<feMerge><feMergeNode in="FillPaint"/></feMerge></filter>'
                               '<rect x="5" y="5" width="10" height="10" fill="lime" fill-opacity="0.5" '
                               'filter="url(#f)"/>'))
        assert img[10, 10, 1] == pytest.approx(1.0) and img[10, 10, 3] == pytest.approx(0.5, abs=0.01)

    def test_background_image(self):
        markup = svg('<g enable-background="new"><rect width="20" height="20" fill="blue"/>'
                     '<filter id="f" filterUnits="userSpaceOnUse" x="0" y="0" width="20" height="20">'
                     '<feMerge><feMergeNode in="BackgroundImage"/></feMerge></filter>'
                     '<rect x="5" y="5" width="2" height="2" fill="red" filter="url(#f)"/></g>')
        img = render_float(markup)
        assert img[1, 1, 2] == pytest.approx(1.0) and img[6, 6, 0] == 0
        without = render_float(markup.replace('enable-background="new"', ""))
        np.testing.assert_allclose(without[6, 6], [0, 0, 1, 1], atol=1e-6)

    def test_background_alpha(self):
        img = render_float(svg('<g enable-background="new"><rect width="20" height="20" fill="white" opacity="0.5"/>'
                               '<filter id="f" filterUnits="userSpaceOnUse" x="0" y="0" width="20" height="20">'
                               '<feMerge><feMergeNode in="BackgroundAlpha"/></feMerge></filter>'
                               '<rect width="1" height="1" filter="url(#f)"/></g>'))
        assert img[10, 10, 3] == pytest.approx(0.75, abs=0.02)

    def test_fe_image_data_uri_and_element(self):
        from svgraster.io import encode_png

        px = np.zeros((2, 2, 4), np.uint8)
        px[...] = (0, 255, 0, 255)
        uri = "data:image/png;base64," + base64.b64encode(encode_png(px)).decode()
        img = render_float(svg(f'<filter id="f" filterUnits="userSpaceOnUse" x="0" y="0" width="20" height="20">'
                               f'<feImage href="{uri}" preserveAspectRatio="none"/></filter>'
                               f'<rect width="20" height="20" filter="url(#f)"/>'))
        assert img[10, 10, 1] == pytest.approx(1.0) and img[10, 10, 3] == pytest.approx(1.0)
        img = render_float(svg('<defs><circle id="c" cx="10" cy="10" r="5" fill="red"/></defs>'
                               '<filter id="f" filterUnits="userSpaceOnUse" x="0" y="0" width="20" height="20">'
                               '<feImage href="#c"/></filter><rect width="20" height="20" filter="url(#f)"/>'))
        assert img[10, 10, 0] == pytest.approx(1.0) and img[1, 1, 3] == 0

    def test_kernel_unit_length_and_filter_res(self):
        base = ('<filter id="f"{extra}><feConvolveMatrix order="3" kernelMatrix="0 0 0 1 0 0 0 0 0" {klu}/>'
                '</filter><rect x="2" y="2" width="16" height="16" fill="navy" filter="url(#f)"/>')
        plain = render_float(svg(base.format(extra="", klu=""), 40, 40, 'viewBox="0 0 20 20"'))
        coarse = render_float(svg(base.format(extra="", klu='kernelUnitLength="4"'), 40, 40, 'viewBox="0 0 20 20"'))
        assert not np.allclose(plain, coarse)
        low = render_float(svg(base.format(extra=' filterRes="6"', klu=""), 40, 40, 'viewBox="0 0 20 20"'))
        assert not np.allclose(plain, low) and low[..., 3].max() > 0.5

    def test_primitive_default_subregion_is_filter_region(self):
        img = render_float(svg('<filter id="f" primitiveUnits="objectBoundingBox" x="0" y="0" width="2" height="2">'
                               '<feFlood width="100%" height="100%" flood-color="lime"/><feOffset dx="0.5"/>'
                               '</filter><rect x="0" y="0" width="10" height="10" filter="url(#f)"/>'))
        assert img[5, 12, 1] == pytest.approx(1.0) and img[5, 2, 3] == 0
