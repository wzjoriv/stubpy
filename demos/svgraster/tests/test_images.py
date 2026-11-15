"""PNG and JPEG decoding, resources, and the ``image`` element."""
from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

import svgraster
from svgraster import _backend
from svgraster.io import jpeg
from svgraster.io._huffman import py_decode_scan
from svgraster.io.png import ADAM7, SIGNATURE, _chunk, decode_png, decode_png_rgba, py_unfilter, unfilter
from svgraster.io.resources import ResourceError, load, parse_data_uri
from tests.conftest import native_module, render_float, svg

DATA = Path(__file__).parent / "data"


def _read(name: str) -> np.ndarray:
    return decode_png_rgba((DATA / name).read_bytes())


@pytest.fixture(scope="module")
def source() -> np.ndarray:
    return _read("source.png").astype(int)


class TestPng:
    @pytest.mark.parametrize("name,tolerance", [("rgba_paeth.png", 0), ("rgb48.png", 1), ("pal8.png", 40)])
    def test_color_types_match_source(self, source, name, tolerance):
        img = _read(name).astype(int)
        assert img.shape == source.shape
        assert np.abs(img[..., :3] - source[..., :3]).mean() <= tolerance

    @pytest.mark.parametrize("name", ["gray16.png", "graya.png"])
    def test_gray_types_are_gray(self, name):
        img = _read(name)
        assert (img[..., 0] == img[..., 1]).all() and (img[..., 1] == img[..., 2]).all()

    def test_adam7_interlaced(self, rng):
        pixels = (rng.random((13, 11, 4)) * 255).astype(np.uint8)
        raw = b""
        for x0, y0, dx, dy in ADAM7:
            sub = pixels[y0::dy, x0::dx]
            if sub.size:
                raw += b"".join(b"\x00" + row.tobytes() for row in sub)
        header = struct.pack(">IIBBBBB", 11, 13, 8, 6, 0, 0, 1)
        data = SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")
        np.testing.assert_array_equal(decode_png_rgba(data), pixels)

    def test_transparency_key_and_rgb_output(self, source):
        assert decode_png((DATA / "source.png").read_bytes()).shape[2] == 3
        assert decode_png((DATA / "rgba_paeth.png").read_bytes()).shape[2] == 4

    def test_corrupt_png(self):
        with pytest.raises(ValueError):
            decode_png_rgba(b"\x89PNG\r\n\x1a\nnope")
        with pytest.raises(ValueError):
            decode_png_rgba(b"GIF89a")

    def test_native_unfilter_matches_python(self, rng):
        native_module("_codec")
        h, stride, bpp = 9, 24, 4
        rows = [bytes([k % 5]) + rng.integers(0, 256, stride, dtype=np.uint8).tobytes() for k in range(h)]
        raw = b"".join(rows)
        np.testing.assert_array_equal(unfilter(raw, h, stride, bpp), py_unfilter(raw, h, stride, bpp))


class TestJpeg:
    @pytest.mark.parametrize("name", ["ycc420", "ycc422", "ycc444"])
    def test_matches_reference_decoder(self, name):
        img = jpeg.decode_jpeg((DATA / f"{name}.jpg").read_bytes()).astype(int)
        ref = _read(f"{name}_ref.png").astype(int)
        assert img.shape[:2] == ref.shape[:2]
        assert np.abs(img[..., :3] - ref[..., :3]).max() <= 4

    def test_native_and_python_scans_agree(self):
        native_module("_codec")
        data = (DATA / "ycc420.jpg").read_bytes()
        with svgraster.pure_python():
            assert _backend.native("codec") is None
            fallback = jpeg.decode_jpeg(data)
        np.testing.assert_array_equal(jpeg.decode_jpeg(data), fallback)
        assert py_decode_scan is not None

    def test_rejects_progressive(self):
        data = bytearray((DATA / "ycc420.jpg").read_bytes())
        sof = data.index(b"\xff\xc0")
        data[sof + 1] = 0xC2
        with pytest.raises(jpeg.JpegError, match="progressive"):
            jpeg.decode_jpeg(bytes(data))


class TestResources:
    def test_data_uris(self):
        assert parse_data_uri("data:text/plain,hi%20there").data == b"hi there"
        res = parse_data_uri("data:image/png;base64," + base64.b64encode(b"\x89PNGxx").decode())
        assert res.media_type == "image/png" and res.data == b"\x89PNGxx"
        with pytest.raises(ResourceError):
            parse_data_uri("data:nocomma")

    def test_local_and_remote(self, tmp_path):
        doc = svgraster.Document.parse(svg(""), base_dir=tmp_path)
        (tmp_path / "x.jpg").write_bytes(b"\xff\xd8abc")
        assert load("x.jpg#frag", doc).media_type == "image/jpeg"
        assert load("x.jpg#frag", doc).fragment == "frag"
        with pytest.raises(ResourceError, match="remote"):
            load("https://example.com/a.png", doc)
        with pytest.raises(ResourceError):
            load("missing.png", doc)


def _data_uri(path: Path, kind: str) -> str:
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()


class TestImageElement:
    def test_png_data_uri_is_drawn_scaled(self, source):
        uri = _data_uri(DATA / "source.png", "image/png")
        img = svgraster.render(svg(f'<image width="72" height="56" href="{uri}"/>', 72, 56))
        assert img.shape == (56, 72, 4)
        assert np.abs(img[10, 10, :3].astype(int) - source[5, 5, :3]).max() < 30

    def test_relative_file_and_aspect_ratio(self, tmp_path):
        (tmp_path / "pic.jpg").write_bytes((DATA / "ycc420.jpg").read_bytes())
        doc = tmp_path / "doc.svg"
        doc.write_text(svg('<image x="0" y="0" width="36" height="56" href="pic.jpg"/>', 36, 56))
        img = svgraster.render(doc)
        alpha = img[..., 3]
        assert alpha[0, 18] == 0 and alpha[28, 18] == 255
        doc.write_text(svg('<image width="36" height="56" preserveAspectRatio="xMidYMid slice" href="pic.jpg"/>',
                           36, 56))
        assert (svgraster.render(doc)[..., 3] == 255).all()

    def test_nested_svg_image(self):
        plain = base64.b64encode(svg('<rect width="10" height="10" fill="lime"/>', 10, 10).encode()).decode()
        img = render_float(svg(f'<image width="20" height="20" href="data:image/svg+xml;base64,{plain}"/>'))
        assert img[5, 5, 1] == pytest.approx(1.0) and img[15, 15, 3] == 0
        boxed = base64.b64encode(svg('<rect width="10" height="10" fill="lime"/>', 10, 10,
                                     'viewBox="0 0 10 10"').encode()).decode()
        img = render_float(svg(f'<image width="20" height="20" href="data:image/svg+xml;base64,{boxed}"/>'))
        assert img[15, 15, 1] == pytest.approx(1.0) and img[15, 15, 3] == pytest.approx(1.0)

    def test_missing_image_warns_and_skips(self):
        with pytest.warns(UserWarning, match="not rendered"):
            img = render_float(svg('<image width="20" height="20" href="does-not-exist.png"/>'))
        assert img[..., 3].max() == 0

    def test_nearest_rendering_keeps_hard_edges(self):
        px = np.zeros((2, 2, 4), np.uint8)
        px[..., 3] = 255
        px[0, 0, :3] = 255
        from svgraster.io import encode_png

        uri = "data:image/png;base64," + base64.b64encode(encode_png(px)).decode()
        smooth = render_float(svg(f'<image width="20" height="20" href="{uri}"/>'))
        crisp = render_float(svg(f'<image width="20" height="20" image-rendering="optimizeSpeed" href="{uri}"/>'))
        assert set(np.unique(crisp[..., 0])) <= {0.0, 1.0}
        assert len(np.unique(smooth[..., 0])) > 2
