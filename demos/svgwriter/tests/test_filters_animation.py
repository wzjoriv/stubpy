from __future__ import annotations

import math

import pytest

import svgwriter as svg
from svgwriter.elements.filters import (
    BlendMode,
    Channel,
    ColorMatrixType,
    CompositeOperator,
    EdgeMode,
    FeBlend,
    FeColorMatrix,
    FeComponentTransfer,
    FeComposite,
    FeConvolveMatrix,
    FeDiffuseLighting,
    FeDisplacementMap,
    FeDistantLight,
    FeFlood,
    FeFunc,
    FeFuncA,
    FeFuncB,
    FeFuncG,
    FeFuncR,
    FeGaussianBlur,
    FeImage,
    FeMerge,
    FeMorphology,
    FeOffset,
    FePointLight,
    FeSpecularLighting,
    FeSpotLight,
    FeTile,
    FeTurbulence,
    Filter,
    MorphologyOperator,
    StandardInput,
    TransferType,
    TurbulenceType,
)

from .conftest import roundtrip, wellformed


def test_primitive_inputs_chain_by_result() -> None:
    blur = FeGaussianBlur(3, in_=StandardInput.SOURCE_ALPHA, result="blur")
    offset = FeOffset(2, 2, in_=blur)
    assert offset.get("in") == "blur"
    blend = FeBlend(BlendMode.MULTIPLY, in_=StandardInput.SOURCE_GRAPHIC, in2=offset)
    assert blend.get("in2") == offset.result == offset.get("result")
    assert FeBlend().get("mode") is None


def test_composite_arithmetic() -> None:
    comp = FeComposite(CompositeOperator.ARITHMETIC, k1=0, k2=1, k3=1, k4=0, in_="a", in2="b")
    assert str(comp) == '<feComposite in="a" in2="b" operator="arithmetic" k1="0" k2="1" k3="1" k4="0"/>'


def test_color_matrix_variants() -> None:
    assert FeColorMatrix.saturate(0.5).get("type") is ColorMatrixType.SATURATE
    assert 'type="hueRotate" values="90"' in str(FeColorMatrix.hue_rotate(90))
    assert 'type="luminanceToAlpha"' in str(FeColorMatrix.luminance_to_alpha())
    grey = FeColorMatrix.grayscale()
    assert len(grey.get("values")) == 20
    with pytest.raises(ValueError):
        FeColorMatrix(values=[1, 2, 3])


def test_convolve_matrix() -> None:
    conv = FeConvolveMatrix([0, -1, 0, -1, 5, -1, 0, -1, 0], edge_mode=EdgeMode.NONE, preserve_alpha=True, target_x=1)
    text = str(conv)
    assert 'kernelMatrix="0 -1 0 -1 5 -1 0 -1 0"' in text and 'preserveAlpha="true"' in text and 'edgeMode="none"' in text
    with pytest.raises(ValueError):
        FeConvolveMatrix([1, 2], order=(2, 2))


def test_component_transfer_and_evaluate() -> None:
    transfer = FeComponentTransfer(
        red=FeFunc.linear(0.5, 0.25),
        green=FeFunc.table(0, 1, 0),
        blue=FeFunc.gamma(2, 2, 0),
        alpha=FeFuncA(TransferType.DISCRETE, table_values=[0, 1]),
    )
    tags = [child.tag for child in transfer]
    assert tags == ["feFuncR", "feFuncG", "feFuncB", "feFuncA"]
    r, g, b, a = transfer
    assert r.evaluate(1.0) == pytest.approx(0.75)
    assert g.evaluate(0.5) == pytest.approx(1.0)
    assert b.evaluate(0.5) == pytest.approx(0.5)
    assert a.evaluate(0.4) == 0 and a.evaluate(0.6) == 1
    assert FeFuncR().evaluate(0.3) == 0.3
    parsed = svg.parse(str(svg.Filter(transfer)))
    assert parsed.find(FeFuncG).evaluate(0.5) == pytest.approx(1.0)  # type: ignore[union-attr]
    assert isinstance(FeFuncB(), FeFunc) and isinstance(FeFuncG(), FeFunc)


def test_lighting() -> None:
    distant = FeDistantLight(azimuth=0, elevation=90)
    assert distant.directional
    assert distant.light_vector(0, 0, 0) == pytest.approx((0, 0, 1))
    point = FePointLight(0, 0, 10)
    assert not point.directional
    assert point.light_vector(0, 0, 0) == pytest.approx((0, 0, 1))
    spot = FeSpotLight(1, 2, 3, points_at_x=4, limiting_cone_angle=30, specular_exponent=8)
    assert 'pointsAtX="4"' in str(spot) and 'limitingConeAngle="30"' in str(spot)
    diffuse = FeDiffuseLighting(distant, surface_scale=2, diffuse_constant=1, lighting_color="white")
    assert diffuse.light is distant
    specular = FeSpecularLighting(point, specular_exponent=20, specular_constant=0.75)
    assert 'specularExponent="20"' in str(specular)


def test_remaining_primitives_serialize() -> None:
    items = [
        FeDisplacementMap(10, Channel.RED, Channel.G, in_="a", in2="b"),
        FeFlood("tomato", 0.5),
        FeImage("tile.png", preserve_aspect_ratio="none"),
        FeMorphology(MorphologyOperator.DILATE, (2, 1)),
        FeTile(in_="a"),
        FeTurbulence((0.05, 0.1), 3, seed=4, stitch_tiles=True, type=TurbulenceType.FRACTAL_NOISE),
        FeMerge("a", StandardInput.SOURCE_GRAPHIC),
    ]
    flt = Filter(*items, filter_units="userSpaceOnUse", primitive_units="objectBoundingBox", filter_res=(100, 100), x=0, width=200)
    text = flt.to_string()
    wellformed(text)
    assert 'xChannelSelector="R"' in text
    assert 'baseFrequency="0.05 0.1"' in text and 'stitchTiles="stitch"' in text
    assert 'filterRes="100 100"' in text
    assert len(flt.primitives) == len(items)
    assert Channel.RED is Channel.R
    first, second = roundtrip(svg.Svg(svg.Defs(flt)))
    assert first == second


def test_animation_elements() -> None:
    fade = svg.Animate.fade(1, 0, dur=2, begin="click", fill=svg.AnimationFill.FREEZE, repeat_count=float("inf"))
    assert str(fade) == '<animate attributeName="opacity" from="1" to="0" begin="click" dur="2s" repeatCount="indefinite" fill="freeze"/>'
    keyed = svg.Animate(
        attribute_name="x",
        values=[0, 10, 0],
        key_times=(0, 0.5, 1),
        key_splines=[(0.5, 0, 0.5, 1), (0.5, 0, 0.5, 1)],
        calc_mode=svg.CalcMode.SPLINE,
        restart=svg.Restart.NEVER,
        additive=svg.Additive.SUM,
        accumulate=svg.Accumulate.SUM,
    )
    text = str(keyed)
    assert 'values="0;10;0"' in text and 'keyTimes="0;0.5;1"' in text
    assert 'keySplines="0.5 0 0.5 1;0.5 0 0.5 1"' in text and 'restart="never"' in text
    assert 'restart' not in str(svg.Animate())
    assert str(svg.Set("visibility", "hidden", begin=1)) == '<set attributeName="visibility" begin="1s" to="hidden"/>'
    assert 'attributeName="fill"' in str(svg.AnimateColor(attribute_name="fill", from_="red", to="blue"))
    spin = svg.AnimateTransform.spin(5, 5, dur=3)
    assert str(spin) == '<animateTransform attributeName="transform" from="0 5 5" to="360 5 5" dur="3s" repeatCount="indefinite" type="rotate"/>'
    route = svg.Path("M0 0 L10 10", id="route")
    motion = svg.AnimateMotion(svg.MPath(route), rotate="auto", key_points=[0, 1], dur=5)
    assert '<mpath xlink:href="#route"/>' in str(motion)
    motion2 = svg.AnimateMotion(path=svg.PathBuilder().move_to(0, 0).line_to(5, 5))
    assert 'path="M0 0 L5 5"' in str(motion2)


def test_animation_round_trip() -> None:
    circle = svg.Circle(5, 5, 2)
    circle.append(svg.Animate(attribute_name="r", from_=2, to=4, dur=1, repeat_count=math.inf))
    first, second = roundtrip(svg.Svg(circle))
    assert first == second
