"""The compiled modules and the thin Python layer, one binding style at a time."""
from __future__ import annotations

import importlib

import numpy as np
import pytest

import svgraster
from svgraster import _jit
from svgraster.filters import BlendMode, LightSource, ResampleFilter, TransferFunction, TransferType, blur
from svgraster.raster import HuffmanTable, Rasterizer, make_packer, make_rasterizer, over

SQUARE = np.array([[1, 1], [7, 1], [7, 7], [1, 7]], dtype=np.float64)


def native(name: str):
    try:
        return importlib.import_module(f"svgraster.{name}")
    except ImportError:
        pytest.skip(f"svgraster.{name} is not built")


def rgba(h=4, w=4, value=0.5) -> np.ndarray:
    return np.full((h, w, 4), value, dtype=np.float32)


def test_backend_info_lists_every_module():
    assert set(svgraster.backend_info()) == set(svgraster.NATIVE_MODULES)


def test_c_api_functions_and_constants():
    scan = native("_scanline")
    assert scan.polygon_area(SQUARE) == pytest.approx(36.0)
    out = np.zeros((8, 8), dtype=np.float32)
    scan.fill_polygons(out, [SQUARE])
    assert out.sum() == pytest.approx(36.0)
    assert scan.NONZERO == 0 and scan.EVENODD == 1 and isinstance(scan.HAVE_OPENMP, bool)
    assert isinstance(scan.version(), str)


def test_c_api_type_properties():
    scan = native("_scanline")
    canvas = scan.Rasterizer(5, 3, samples=2)
    assert (canvas.width, canvas.height, canvas.samples) == (5, 3, 2)
    canvas.samples = 8
    assert canvas.samples == 8
    with pytest.raises(AttributeError):
        canvas.width = 1
    assert scan.Rasterizer.from_shape((3, 5)).width == 5


def test_rasterizer_subclass_forwards_keywords():
    native("_scanline")
    canvas = make_rasterizer(8, 8, samples=8, rule="evenodd")
    assert canvas.samples == 8 and canvas.rule == "evenodd"
    canvas.fill([SQUARE])
    assert canvas.array().shape == (8, 8)
    assert canvas.total() == pytest.approx(36.0)
    assert isinstance(Rasterizer(2, 2), Rasterizer)


def test_cython_enums_and_unfilter():
    codec = native("_codec")
    assert codec.PngFilter.PAETH == 4 and codec.TableClass.AC == 1
    raw = np.array([1, 5, 5, 5], dtype=np.uint8)
    assert codec.unfilter(raw, 1, 3, 1).tolist() == [[5, 10, 15]]
    with pytest.raises(codec.CodecError):
        codec.unfilter(raw[:2], 1, 3, 1)
    assert issubclass(codec.CodecError, ValueError)


def test_cython_extension_type_and_subclass():
    codec = native("_codec")
    table = codec.HuffmanTable([0, 2] + [0] * 14, [7, 9])
    assert table.max_length == 2 and table.table_class == codec.TableClass.DC
    assert table.packed().dtype == np.int32
    with pytest.raises(AttributeError):
        table.table_class = codec.TableClass.AC
    assert HuffmanTable.uniform(4, table_class=codec.TableClass.AC).table_class == codec.TableClass.AC


def test_cython_ycbcr_gray_passes_through():
    codec = native("_codec")
    plane = np.full((2, 2), 100.0)
    rgb = codec.ycbcr_to_rgb(plane, np.full((2, 2), 128.0), np.full((2, 2), 128.0))
    assert rgb.shape == (2, 2, 3) and (rgb == 100).all()


def test_cython_without_embedsignature_pattern_tile():
    pattern = native("_pattern")
    tile = rgba(2, 2, 1.0)
    out = np.zeros((4, 4, 4), dtype=np.float32)
    inv = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    pattern.PatternTile(tile).fill(out, inv)
    assert out.min() == 1.0
    assert pattern.PatternTile(tile).width == 2


def test_pybind11_overloads_and_enums():
    filters = native("_filters")
    img = rgba()
    assert filters.gaussian_blur(img, 1.0).shape == filters.gaussian_blur(img, 1.0, 2.0).shape == (4, 4, 4)
    assert filters.flood(2, 3, (1, 0, 0, 1)).shape == (2, 3, 4)
    assert filters.flood(img, (0, 0, 0, 0)).sum() == 0
    assert sum(filters.gaussian_kernel(1.5)) == pytest.approx(1.0)
    assert filters.resample(img, 8, 8, filter=ResampleFilter.NEAREST).shape == (8, 8, 4)
    assert filters.blend(img, img, BlendMode.MULTIPLY).shape == (4, 4, 4)


def test_pybind11_classes():
    transfer = TransferFunction(TransferType.TABLE, [0.0, 1.0])
    assert transfer(0.5) == pytest.approx(0.5) and transfer.kind == TransferType.TABLE
    assert TransferFunction(2.0)(0.25) == pytest.approx(0.5)
    light = LightSource(1.0, 2.0, 3.0)
    light.position = (4.0, 5.0, 6.0)
    assert light.position == [4.0, 5.0, 6.0]
    with pytest.raises(AttributeError):
        light.kind = None


def test_filters_layer_forwards_keywords():
    native("_filters")
    assert blur(rgba(), 1.0, sy=0.5).shape == (4, 4, 4)


def test_nanobind_compositing_and_packing():
    comp = native("_composite")
    dst = rgba(value=0.0)
    assert over(dst, rgba(value=1.0), opacity=0.5)[0, 0, 0] == pytest.approx(0.5)
    assert comp.LineJoin.MITER.value == 0
    packer = make_packer(4, 4, format=comp.PixelFormat.RGB)
    assert len(packer.pack(rgba())) == packer.frame_bytes == 48 and packer.frames == 1
    packer.format = comp.PixelFormat.RGBA
    assert packer.frame_bytes == 64
    with pytest.raises(AttributeError):
        packer.width = 8


def test_numba_functions_match_numpy():
    img = np.arange(4 * 4 * 4, dtype=np.float32).reshape(4, 4, 4)
    assert np.allclose(_jit.downscale(img, 2), _jit.downscale(img, 2, use_jit=False))
    px = np.full((2, 2, 4), 255, dtype=np.uint8)
    assert np.allclose(_jit.premultiply_u8(px), _jit.premultiply_u8(px, use_jit=False))
