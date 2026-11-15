from __future__ import annotations

import pytest

from svgwriter.color import NAMED_COLORS, Color, PaintKeyword, PaintRef, clamp, parse_color, parse_paint
from svgwriter.attributes import FuncIRI


def test_named_color_count() -> None:
    assert len(NAMED_COLORS) == 147
    assert NAMED_COLORS["purple"] == (128, 0, 128)
    assert "rebeccapurple" not in NAMED_COLORS


@pytest.mark.parametrize(
    ("text", "rgb"),
    [
        ("red", (255, 0, 0)),
        ("ReD", (255, 0, 0)),
        ("#f80", (255, 136, 0)),
        ("#FF8800", (255, 136, 0)),
        ("rgb(1, 2, 3)", (1, 2, 3)),
        ("rgb(100%, 50%, 0%)", (255, 128, 0)),
        ("rgb(300, -5, 0)", (255, 0, 0)),
    ],
)
def test_parse(text: str, rgb: tuple[int, int, int]) -> None:
    assert parse_color(text).rgb == rgb


@pytest.mark.parametrize("bad", ["#12", "#1234567", "rgb(1,2)", "rgb(1%,2,3)", "notacolor"])
def test_parse_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_color(bad)


def test_named_colors_keep_their_name() -> None:
    assert str(parse_color("tomato")) == "tomato"
    assert str(Color(255, 99, 71)) == "#ff6347"
    assert parse_color("tomato") == Color(255, 99, 71)


def test_icc_color() -> None:
    color = parse_color("#cd853f icc-color(acmecmyk, 0.11, 0.48, 0.83, 0.00)")
    assert color.rgb == (205, 133, 63)
    assert str(color) == "#cd853f icc-color(acmecmyk, 0.11, 0.48, 0.83, 0.00)"


def test_channel_validation() -> None:
    with pytest.raises(ValueError):
        Color(256, 0, 0)


def test_conversions() -> None:
    orange = Color(255, 128, 0)
    assert orange.to_percent() == "rgb(100%,50.1961%,0%)"
    assert Color.from_floats(1.0, 0.5, 0.0) == Color(255, 128, 0)
    h, s, l = Color(255, 0, 0).hsl
    assert (h, s, l) == pytest.approx((0.0, 1.0, 0.5))
    assert Color.from_hsl(120, 1, 0.5) == Color(0, 255, 0)


def test_lighten_darken_mix() -> None:
    red = Color(255, 0, 0)
    assert red.lighten(0.5) == Color(255, 255, 255)
    assert red.darken(0.5) == Color(0, 0, 0)
    assert red.mix(Color(0, 0, 255)).hex == "#800080"
    assert red.mix(Color(0, 0, 255), 0).hex == "#ff0000"


def test_luminance() -> None:
    assert Color(255, 255, 255).luminance == pytest.approx(1.0)
    assert Color(0, 0, 0).luminance == 0.0


def test_clamp_constrained_typevar() -> None:
    assert clamp(5, 0, 3) == 3
    assert clamp(-1.5, 0.0, 1.0) == 0.0


def test_parse_paint() -> None:
    assert parse_paint("none") is PaintKeyword.NONE
    assert parse_paint("currentColor") is PaintKeyword.CURRENT_COLOR
    assert parse_paint("blue") == Color(0, 0, 255)
    ref = parse_paint("url(#grad) red")
    assert ref == PaintRef(FuncIRI("#grad"), Color(255, 0, 0))
    assert str(ref) == "url(#grad) red"
    assert str(parse_paint("url(#g) none")) == "url(#g) none"
    with pytest.raises(ValueError):
        parse_paint("url(#a) url(#b)")
