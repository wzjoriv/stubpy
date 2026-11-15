"""End-to-end rendering: known pixels for shapes, paint, clipping, masking, filters and text."""
from __future__ import annotations

import numpy as np
import pytest

import svgraster
from svgraster import Renderer
from svgraster.render.renderer import intrinsic_size
from tests.conftest import render_float, svg

RED = [255, 0, 0, 255]
CLEAR = [0, 0, 0, 0]


def px(img, x, y):
    return img[y, x].tolist()


class TestShapes:
    def test_rect_fill_and_edges(self):
        img = svgraster.render(svg('<rect x="2.5" y="2" width="10" height="6" fill="red"/>'))
        assert img.shape == (20, 20, 4) and img.dtype == np.uint8
        assert px(img, 5, 4) == RED and px(img, 0, 0) == CLEAR
        assert px(img, 2, 4) == [255, 0, 0, 128]

    @pytest.mark.parametrize("element", [
        '<circle cx="10" cy="10" r="6"/>', '<ellipse cx="10" cy="10" rx="8" ry="4"/>',
        '<rect x="4" y="4" width="12" height="12" rx="3"/>', '<polygon points="10,2 18,18 2,18"/>',
        '<path d="M4 4 H16 V16 H4 Z"/>',
    ])
    def test_basic_shapes_cover_center(self, element):
        img = render_float(svg(element))
        assert img[10, 10, 3] == pytest.approx(1.0) and img[0, 0, 3] == 0.0

    def test_circle_area(self):
        img = render_float(svg('<circle cx="10" cy="10" r="7"/>'), antialias=64, tolerance=0.002)
        assert img[..., 3].sum() == pytest.approx(np.pi * 49, rel=2e-3)

    def test_fill_rules(self):
        d = "M2 2 H18 V18 H2 Z M6 6 H14 V14 H6 Z"
        nonzero = render_float(svg(f'<path d="{d}"/>'))
        evenodd = render_float(svg(f'<path d="{d}" fill-rule="evenodd"/>'))
        assert nonzero[10, 10, 3] == 1.0 and evenodd[10, 10, 3] == 0.0 and evenodd[3, 3, 3] == 1.0

    def test_stroke_and_opacity(self):
        img = render_float(svg('<line x1="2" y1="10" x2="18" y2="10" stroke="blue" stroke-width="4" '
                               'stroke-opacity="0.5"/>'))
        assert img[10, 10].tolist() == pytest.approx([0, 0, 1, 0.5]) and img[5, 10, 3] == 0

    def test_dashes_caps_and_joins(self):
        img = render_float(svg('<polyline points="2,10 18,10" stroke="black" stroke-width="2" '
                               'stroke-dasharray="4 4"/>'))
        assert img[10, 4, 3] == 1.0 and img[10, 8, 3] == 0.0 and img[10, 12, 3] == 1.0
        capped = render_float(svg('<line x1="5" y1="10" x2="15" y2="10" stroke="black" stroke-width="4" '
                                  'stroke-linecap="square"/>'))
        assert capped[10, 4, 3] == 1.0
        dot = render_float(svg('<path d="M10 10 Z" stroke="black" stroke-width="6" stroke-linecap="round"/>'))
        assert dot[10, 10, 3] == 1.0

    def test_group_opacity_is_applied_once(self):
        img = render_float(svg('<g opacity="0.5"><rect width="10" height="10" fill="red"/>'
                               '<rect width="10" height="10" fill="red"/></g>'))
        assert img[5, 5, 3] == pytest.approx(0.5)

    def test_display_and_visibility(self):
        img = render_float(svg('<rect width="10" height="10" display="none"/>'
                               '<g visibility="hidden"><rect x="10" width="10" height="10"/>'
                               '<rect x="10" y="10" width="10" height="10" visibility="visible"/></g>'))
        assert img[5, 5, 3] == 0 and img[5, 15, 3] == 0 and img[15, 15, 3] == 1.0


class TestStructure:
    def test_transforms_and_viewbox(self):
        img = render_float(svg('<rect width="1" height="1" fill="red" transform="translate(5 0)"/>',
                               40, 20, 'viewBox="0 0 10 5"'))
        assert img[2, 21, 0] == 1.0 and img[2, 18, 3] == 0.0

    def test_preserve_aspect_ratio(self):
        img = render_float(svg('<rect width="10" height="10"/>', 40, 20, 'viewBox="0 0 10 10"'))
        assert img[10, 20, 3] == 1.0 and img[10, 5, 3] == 0.0

    def test_use_and_symbol(self):
        img = render_float(svg('<defs><rect id="r" width="4" height="4" fill="red"/>'
                               '<symbol id="s" viewBox="0 0 1 1"><rect width="1" height="1" fill="blue"/></symbol>'
                               '</defs><use href="#r" x="2" y="2"/><use xlink:href="#s" x="10" y="10" width="6" '
                               'height="6"/>'))
        assert img[3, 3, 0] == 1.0 and img[12, 12, 2] == 1.0 and img[8, 8, 3] == 0

    def test_use_inherits_style_from_use(self):
        img = render_float(svg('<defs><rect id="r" width="5" height="5"/></defs><use href="#r" fill="lime"/>'))
        assert img[2, 2, :3].tolist() == pytest.approx([0, 1, 0])

    def test_nested_svg_clips(self):
        img = render_float(svg('<svg x="5" y="5" width="5" height="5"><rect width="20" height="20"/></svg>'))
        assert img[7, 7, 3] == 1.0 and img[12, 12, 3] == 0.0

    def test_css_and_current_color(self):
        img = render_float(svg('<style>.c { fill: currentColor }</style>'
                               '<g color="blue"><rect class="c" width="5" height="5"/></g>'))
        assert img[2, 2, :3].tolist() == pytest.approx([0, 0, 1])

    def test_markers(self):
        img = render_float(svg('<marker id="m" markerWidth="4" markerHeight="4" refX="2" refY="2" '
                               'markerUnits="userSpaceOnUse"><rect width="4" height="4" fill="red"/></marker>'
                               '<polyline points="4,4 16,4 16,16" fill="none" stroke="none" '
                               'marker-start="url(#m)" marker-mid="url(#m)" marker-end="url(#m)"/>'))
        assert img[4, 4, 0] == 1.0 and img[4, 16, 0] == 1.0 and img[16, 16, 0] == 1.0
        assert img[10, 10, 3] == 0.0


class TestPaintServers:
    def test_linear_gradient(self):
        img = render_float(svg('<linearGradient id="g"><stop offset="0" stop-color="red"/>'
                               '<stop offset="1" stop-color="blue"/></linearGradient>'
                               '<rect width="100" height="10" fill="url(#g)"/>', 100, 10))
        assert img[5, 0, 0] > 0.99 and img[5, 99, 2] > 0.99
        assert img[5, 49, 0] == pytest.approx(0.5, abs=0.01)

    def test_gradient_href_units_and_spread(self):
        img = render_float(svg('<linearGradient id="a" spreadMethod="repeat"><stop offset="0" stop-color="black"/>'
                               '<stop offset="1" stop-color="white"/></linearGradient>'
                               '<linearGradient id="b" href="#a" gradientUnits="userSpaceOnUse" x1="0" x2="10"/>'
                               '<rect width="20" height="2" fill="url(#b)"/>', 20, 2))
        assert img[1, 5, 0] == pytest.approx(img[1, 15, 0], abs=1e-6)

    def test_radial_gradient_and_fallback(self):
        img = render_float(svg('<radialGradient id="g"><stop offset="0" stop-color="white"/>'
                               '<stop offset="1" stop-color="black"/></radialGradient>'
                               '<circle cx="10" cy="10" r="10" fill="url(#g)"/>'
                               '<rect width="2" height="2" fill="url(#missing) red"/>'))
        assert img[10, 10, 0] > 0.9 and img[10, 19, 0] < 0.15 and img[0, 0, 0] == 1.0

    def test_pattern(self):
        img = render_float(svg('<pattern id="p" width="4" height="4" patternUnits="userSpaceOnUse">'
                               '<rect width="2" height="2" fill="red"/></pattern>'
                               '<rect width="20" height="20" fill="url(#p)"/>'))
        assert img[1, 1, 3] == 1.0 and img[3, 3, 3] == 0.0 and img[9, 9, 3] == 1.0 and img[11, 11, 3] == 0.0


class TestEffects:
    def test_clip_path(self):
        img = render_float(svg('<clipPath id="c"><circle cx="10" cy="10" r="5"/></clipPath>'
                               '<rect width="20" height="20" fill="red" clip-path="url(#c)"/>'))
        assert img[10, 10, 3] == 1.0 and img[1, 1, 3] == 0.0

    def test_clip_path_object_bounding_box(self):
        img = render_float(svg('<clipPath id="c" clipPathUnits="objectBoundingBox">'
                               '<rect width="0.5" height="1"/></clipPath>'
                               '<rect x="4" y="4" width="12" height="12" clip-path="url(#c)"/>'))
        assert img[10, 6, 3] == 1.0 and img[10, 14, 3] == 0.0

    def test_mask(self):
        img = render_float(svg('<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="20" height="20">'
                               '<rect width="10" height="20" fill="white"/>'
                               '<rect x="10" width="10" height="20" fill="#808080"/></mask>'
                               '<rect width="20" height="20" fill="red" mask="url(#m)"/>'))
        assert img[5, 5, 3] == pytest.approx(1.0) and img[5, 15, 3] == pytest.approx(0.502 * 0.9999, abs=0.01)

    def test_filter_flood_and_offset(self):
        img = render_float(svg('<filter id="f" x="0" y="0" width="1" height="1"><feFlood flood-color="lime"/>'
                               '</filter><rect x="5" y="5" width="10" height="10" fill="red" filter="url(#f)"/>'))
        assert img[10, 10, :3].tolist() == pytest.approx([0, 1, 0], abs=1e-5) and img[2, 2, 3] == 0
        img = render_float(svg('<filter id="f"><feOffset dx="3" dy="0"/></filter>'
                               '<rect x="5" y="5" width="6" height="6" fill="red" filter="url(#f)"/>'))
        assert img[8, 6, 3] == 0.0 and img[8, 9, 3] == 1.0 and img[8, 12, 3] == 0.0

    def test_filter_blur_and_region(self):
        img = render_float(svg('<filter id="f"><feGaussianBlur stdDeviation="2"/></filter>'
                               '<rect x="6" y="6" width="8" height="8" fill="black" filter="url(#f)"/>'))
        assert 0.0 < img[10, 5, 3] < 1.0 and img[0, 0, 3] == 0.0

    def test_filter_chain_named_results(self):
        img = render_float(svg('<filter id="f" x="0" y="0" width="1" height="1">'
                               '<feFlood flood-color="blue" result="b"/>'
                               '<feComposite in="SourceGraphic" in2="b" operator="over"/></filter>'
                               '<circle cx="10" cy="10" r="10" fill="red" filter="url(#f)"/>'))
        assert img[10, 10, 0] == pytest.approx(1.0, abs=1e-5) and img[0, 0, 2] == pytest.approx(1.0, abs=1e-5)

    def test_filter_on_empty_bbox_hides_element(self):
        img = render_float(svg('<filter id="f"><feFlood flood-color="red"/></filter>'
                               '<line x1="0" y1="5" x2="20" y2="5" stroke="black" filter="url(#f)"/>'))
        assert img[..., 3].sum() == 0

    def test_color_interpolation_filters(self):
        body = ('<filter id="f" x="0" y="0" width="1" height="1" color-interpolation-filters="{}">'
                '<feComponentTransfer><feFuncR type="linear" slope="0.5"/></feComponentTransfer></filter>'
                '<rect width="20" height="20" fill="red" filter="url(#f)"/>')
        linear = render_float(svg(body.format("linearRGB")))
        srgb = render_float(svg(body.format("sRGB")))
        assert srgb[5, 5, 0] == pytest.approx(0.5, abs=1e-5)
        assert linear[5, 5, 0] == pytest.approx(0.7354, abs=2e-3)


class TestTextAndOptions:
    def test_text_draws_glyphs(self):
        img = render_float(svg('<text x="2" y="16" font-size="14" fill="black">HI</text>', 30, 20))
        assert img[..., 3].sum() > 20 and img[1, 1, 3] == 0

    def test_text_anchor_moves_text(self):
        start = render_float(svg('<text x="20" y="15" font-size="10">A</text>', 40, 20))
        end = render_float(svg('<text x="20" y="15" font-size="10" text-anchor="end">A</text>', 40, 20))
        assert start[..., 3][:, :20].sum() < end[..., 3][:, :20].sum()

    def test_sizes_dpi_and_background(self):
        doc = svg('<rect width="1in" height="1in" fill="red"/>', extra='').replace('width="20" height="20"',
                                                                                  'width="2in" height="1in"')
        assert svgraster.render(doc).shape == (96, 192, 4)
        assert svgraster.render(doc, dpi=48).shape == (48, 96, 4)
        assert svgraster.render(doc, width=50).shape == (25, 50, 4)
        img = svgraster.render(doc, dpi=48, background="white")
        assert px(img, 70, 10) == [255, 255, 255, 255] and px(img, 10, 10) == RED

    def test_intrinsic_size_rules(self):
        from svgraster.dom import Document
        assert intrinsic_size(Document.parse('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 10"/>')) \
            == (30, 10)
        assert intrinsic_size(Document.parse('<svg xmlns="http://www.w3.org/2000/svg" width="60" '
                                             'viewBox="0 0 30 10"/>')) == (60, 20)
        assert intrinsic_size(Document.parse('<svg xmlns="http://www.w3.org/2000/svg"/>')) == (100, 100)

    def test_dtypes_and_premultiplied(self):
        doc = svg('<rect width="20" height="20" fill="red" fill-opacity="0.5"/>')
        straight = svgraster.render(doc, dtype="float32")
        premul = Renderer().render(doc, dtype="float32", premultiplied=True)
        assert straight[5, 5].tolist() == pytest.approx([1, 0, 0, 0.5]) and premul[5, 5, 0] == pytest.approx(0.5)
        with pytest.raises(ValueError):
            svgraster.render(doc, dtype="int16")

    def test_supersample_matches_analytic(self):
        doc = svg('<circle cx="10" cy="10" r="6"/>')
        a = render_float(doc, supersample=4)
        b = render_float(doc)
        assert np.abs(a[..., 3] - b[..., 3]).max() < 0.08

    def test_renderer_validation(self):
        with pytest.raises(ValueError):
            Renderer(antialias=0)
        with pytest.raises(ValueError):
            Renderer(supersample=99)
        assert "antialias=4" in repr(Renderer(antialias=4, threads=2))

    def test_threads_option(self):
        doc = svg('<filter id="f"><feGaussianBlur stdDeviation="1"/></filter><rect x="5" y="5" width="9" height="9" '
                  'filter="url(#f)"/>')
        np.testing.assert_allclose(Renderer(threads=1).render(doc), Renderer(threads=2).render(doc))

    def test_bytes_and_path_sources(self, tmp_path):
        doc = svg('<rect width="5" height="5"/>')
        path = tmp_path / "a.svg"
        path.write_text(doc)
        np.testing.assert_array_equal(svgraster.render(doc.encode()), svgraster.render(path))
        np.testing.assert_array_equal(svgraster.render(str(path)), svgraster.render_file(path))
