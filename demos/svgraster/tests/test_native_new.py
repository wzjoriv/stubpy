"""The native additions: band-parallel scanline, FramePacker, codec classes and numba resampling."""
from __future__ import annotations

import numpy as np
import pytest

import svgraster
from svgraster import _jit
from svgraster.raster import composite
from svgraster.raster.scanline import py_fill_polygons
from tests.conftest import native_module, svg


def _star(cx: float, cy: float, r: float, n: int = 11) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    rad = np.where(np.arange(2 * n) % 2 == 0, r, r * 0.4)
    return np.column_stack([cx + rad * np.cos(t), cy + rad * np.sin(t)])


@pytest.mark.parametrize("threads", [1, 4])
def test_band_parallel_scanline_matches_fallback(threads):
    mod = native_module("_scanline")
    mod.set_num_threads(threads)
    polys = [_star(90, 70, 65), np.ascontiguousarray(_star(40, 120, 30, 7)[::-1])]
    for rule in (0, 1):
        native = np.zeros((150, 180), np.float32)
        fallback = np.zeros_like(native)
        mod.fill_polygons(native, polys, rule, 8)
        py_fill_polygons(fallback, polys, rule, 8)
        np.testing.assert_allclose(native, fallback, atol=1e-4)
    assert isinstance(mod.HAVE_OPENMP, bool)


def test_frame_packer(rgba):
    mod = native_module("_composite")
    h, w = rgba.shape[:2]
    packer = mod.FramePacker(w, h)
    raw = packer.pack(rgba)
    expected = composite.py_to_uint8(rgba, unpremultiply=True)
    np.testing.assert_array_equal(np.frombuffer(raw, np.uint8).reshape(h, w, 4), expected)
    assert packer.frames == 1 and packer.frame_bytes == h * w * 4 and "frames=1" in repr(packer)
    packer.format = mod.PixelFormat.RGB
    packer.background = (0.0, 0.0, 0.0, 1.0)
    rgb = np.frombuffer(packer.pack(rgba), np.uint8).reshape(h, w, 3)
    np.testing.assert_allclose(rgb, np.floor(np.clip(rgba[..., :3], 0, 1) * 255 + 0.5), atol=1)
    packer.format = mod.PixelFormat.BGRA
    bgra = np.frombuffer(packer.pack(rgba), np.uint8).reshape(h, w, 4)
    np.testing.assert_array_equal(bgra[..., 0], expected[..., 2])
    with pytest.raises(ValueError):
        packer.pack(np.zeros((2, 2, 4), np.float32))
    with pytest.raises(ValueError):
        mod.FramePacker(0, 4)


def test_composite_threads_keep_results(rgba, rgba2):
    mod = native_module("_composite")
    mod.set_num_threads(2)
    big_a = np.tile(rgba, (12, 12, 1))
    big_b = np.tile(rgba2, (12, 12, 1))
    dst = big_a.copy()
    mod.over(dst, big_b, opacity=0.5)
    ref = big_a.copy()
    composite.py_over(ref, big_b, 0.5)
    np.testing.assert_allclose(dst, ref, atol=1e-6)


def test_codec_module_classes():
    mod = native_module("_codec")
    assert int(mod.PngFilter.PAETH) == 4 and int(mod.TableClass.AC) == 1
    table = mod.HuffmanTable([0, 1, 5, 1, 1, 1, 1, 1, 1] + [0] * 7, list(range(12)))
    assert table.max_length == 9 and table.table_class == mod.TableClass.DC
    from svgraster.io._huffman import pack_table

    np.testing.assert_array_equal(table.packed(), pack_table(table.counts, table.values))
    with pytest.raises(ValueError):
        mod.HuffmanTable([1] * 16, [0])
    y = np.full((2, 2), 128.0)
    np.testing.assert_array_equal(mod.ycbcr_to_rgb(y, y, y), np.full((2, 2, 3), 128, np.uint8))


def test_jit_resample_and_premultiply(rgba):
    np.testing.assert_allclose(_jit.resample(rgba, 30, 11), _jit.py_resample(rgba, 30, 11), atol=1e-5)
    u8 = (rgba * 255).astype(np.uint8)
    np.testing.assert_allclose(_jit.premultiply_u8(u8), _jit.py_premultiply_u8(u8), atol=1e-6)


def test_renderer_threads_option():
    markup = svg('<circle cx="10" cy="10" r="8" fill="teal"/>')
    one = svgraster.Renderer(threads=1).render(markup)
    many = svgraster.Renderer(threads=4).render(markup)
    np.testing.assert_array_equal(one, many)
    with pytest.raises(ValueError):
        svgraster.Renderer(threads=0)
