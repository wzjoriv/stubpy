"""Per-primitive handlers mapping filter elements onto :mod:`svgraster.filters`."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from .. import filters as fx
from ..dom.color import Color
from ..dom.node import Node
from ..dom.units import parse_numbers
from ..raster.paint import srgb_to_linear_values
from ._fe_image import fe_image
from ._filtering import LINEAR, FilterContext
from ._servers import style_color

DEFAULT_ORDER = 3
FUNC_TAGS = ("feFuncR", "feFuncG", "feFuncB", "feFuncA")
LIGHT_TAGS = ("feDistantLight", "fePointLight", "feSpotLight")


def _num(prim: Node, name: str, default: float) -> float:
    values = parse_numbers(prim.get(name))
    return values[0] if values else default


def _pair(prim: Node, name: str, default: float) -> tuple[float, float]:
    values = parse_numbers(prim.get(name))
    if not values:
        return default, default
    return values[0], values[1] if len(values) > 1 else values[0]


def _color_in(color: Color, space: str) -> tuple[float, float, float, float]:
    rgb = np.array(color[:3])
    if space == LINEAR:
        rgb = srgb_to_linear_values(rgb)
    return tuple(float(v) for v in rgb) + (color.a,)


def _kernel_unit(ctx: FilterContext, prim: Node) -> tuple[float, float] | None:
    """Pixels per ``kernelUnitLength`` unit, or ``None`` when it is absent or invalid."""
    values = parse_numbers(prim.get("kernelUnitLength"))
    if not values or values[0] <= 0 or (len(values) > 1 and values[1] <= 0):
        return None
    return ctx.px(values[0], "x"), ctx.px(values[1] if len(values) > 1 else values[0], "y")


def _at_kernel_scale(img: np.ndarray, unit: tuple[float, float] | None, fn):
    """Run ``fn(image, (sx, sy))`` on ``img`` resampled so one kernel unit is one pixel."""
    if unit is None:
        return fn(img, (1.0, 1.0))
    h, w = img.shape[:2]
    sh, sw = max(1, round(h / unit[1])), max(1, round(w / unit[0]))
    if (sh, sw) == (h, w):
        return fn(img, (1.0, 1.0))
    result = fn(fx.resample(img, sh, sw), (sw / w, sh / h))
    return fx.resample(result, h, w)


def _premul(color: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    r, g, b, a = color
    return (r * a, g * a, b * a, a)


def blur(ctx: FilterContext, prim: Node, space: str, rect):
    sx, sy = _pair(prim, "stdDeviation", 0.0)
    if sx < 0 or sy < 0:
        return None
    return fx.gaussian_blur(ctx.input(prim.get("in"), space).image, ctx.px(sx, "x"), ctx.px(sy, "y"))


def offset(ctx, prim, space, rect):
    dx, dy = ctx.vector(_num(prim, "dx", 0.0), _num(prim, "dy", 0.0))
    return fx.offset(ctx.input(prim.get("in"), space).image, dx, dy)


def flood(ctx, prim, space, rect):
    color = style_color(prim, "flood-color", "flood-opacity") or Color(0, 0, 0, 1)
    h, w = ctx.shape
    return fx.flood(h, w, _premul(_color_in(color, space)))


def blend(ctx, prim, space, rect):
    src = ctx.input(prim.get("in"), space).image
    backdrop = ctx.input(prim.get("in2"), space).image
    return fx.blend(src, backdrop, prim.get("mode", "normal"))


def composite(ctx, prim, space, rect):
    a = ctx.input(prim.get("in"), space).image
    b = ctx.input(prim.get("in2"), space).image
    k = tuple(_num(prim, name, 0.0) for name in ("k1", "k2", "k3", "k4"))
    return fx.composite(a, b, prim.get("operator", "over"), k)


def color_matrix(ctx, prim, space, rect):
    img = ctx.input(prim.get("in"), space).image
    kind = prim.get("type", "matrix")
    values = parse_numbers(prim.get("values"))
    if kind == "matrix" and len(values) != 20:
        values = []
    return fx.color_matrix(img, kind, values)


def component_transfer(ctx, prim, space, rect):
    specs: list[fx.TransferSpec | None] = [None] * 4
    for child in prim.children:
        if child.tag in FUNC_TAGS:
            specs[FUNC_TAGS.index(child.tag)] = fx.TransferSpec(
                kind=child.get("type", "identity"),
                table=parse_numbers(child.get("tableValues")),
                slope=_num(child, "slope", 1.0), intercept=_num(child, "intercept", 0.0),
                amplitude=_num(child, "amplitude", 1.0), exponent=_num(child, "exponent", 1.0),
                offset=_num(child, "offset", 0.0))
    return fx.component_transfer(ctx.input(prim.get("in"), space).image, specs)


def morphology(ctx, prim, space, rect):
    rx, ry = _pair(prim, "radius", 0.0)
    if rx < 0 or ry < 0:
        return None
    img = ctx.input(prim.get("in"), space).image
    return fx.morphology(img, int(round(ctx.px(rx, "x"))), int(round(ctx.px(ry, "y"))),
                         prim.get("operator", "erode"))


def convolve(ctx, prim, space, rect):
    ox, oy = (int(v) for v in _pair(prim, "order", DEFAULT_ORDER))
    kernel = parse_numbers(prim.get("kernelMatrix"))
    if ox <= 0 or oy <= 0 or len(kernel) != ox * oy:
        return None
    divisor = _num(prim, "divisor", 0.0) or None
    target = (int(_num(prim, "targetX", -1)), int(_num(prim, "targetY", -1)))
    if not (-1 <= target[0] < ox and -1 <= target[1] < oy):
        return None
    return _at_kernel_scale(ctx.input(prim.get("in"), space).image, _kernel_unit(ctx, prim),
                            lambda img, _: fx.convolve_matrix(
                                img, np.array(kernel).reshape(oy, ox), divisor, _num(prim, "bias", 0.0), target,
                                prim.get("edgeMode", "duplicate"), prim.get("preserveAlpha", "false") == "true"))


def tile(ctx, prim, space, rect):
    src = ctx.input(prim.get("in"), space)
    return fx.tile(src.image, src.rect)


def merge(ctx, prim, space, rect):
    layers = [ctx.input(c.get("in"), space).image for c in prim.children if c.tag == "feMergeNode"]
    return fx.merge(layers) if layers else None


def turbulence(ctx, prim, space, rect):
    bfx, bfy = _pair(prim, "baseFrequency", 0.0)
    if bfx < 0 or bfy < 0:
        return None
    h, w = ctx.shape
    inv = ctx.ctm.inverse().as_array()
    tx, ty, tw, th = rect
    user_tile = ctx.ctm.inverse().transform_rect(tx, ty, tw, th)
    tile_rect = (user_tile[0], user_tile[1], user_tile[2] - user_tile[0], user_tile[3] - user_tile[1])
    return fx.turbulence(h, w, inv, (bfx, bfy), int(_num(prim, "numOctaves", 1)), int(_num(prim, "seed", 0)),
                         prim.get("stitchTiles") == "stitch", prim.get("type", "turbulence") == "fractalNoise",
                         tile_rect)


def displacement(ctx, prim, space, rect):
    img = ctx.input(prim.get("in"), space).image
    disp = ctx.input(prim.get("in2"), space).image
    return fx.displacement_map(img, disp, ctx.px(_num(prim, "scale", 0.0), "xy"),
                               prim.get("xChannelSelector", "A"), prim.get("yChannelSelector", "A"))


def _light(ctx: FilterContext, prim: Node) -> fx.LightSpec | None:
    node = next((c for c in prim.children if c.tag in LIGHT_TAGS), None)
    if node is None:
        return None
    if node.tag == "feDistantLight":
        return fx.LightSpec("distant", azimuth=_num(node, "azimuth", 0.0), elevation=_num(node, "elevation", 0.0))

    def point(xs: str, ys: str, zs: str) -> tuple[float, float, float]:
        x, y = ctx.ctm.apply(ctx.user_length(_num(node, xs, 0.0), "x"), ctx.user_length(_num(node, ys, 0.0), "y"))
        return (x, y, ctx.user_length(_num(node, zs, 0.0), "xy") * ctx.scale)

    pos = point("x", "y", "z")
    if node.tag == "fePointLight":
        return fx.LightSpec("point", position=pos)
    cone = node.get("limitingConeAngle")
    return fx.LightSpec("spot", position=pos, points_at=point("pointsAtX", "pointsAtY", "pointsAtZ"),
                        specular_exponent=_num(node, "specularExponent", 1.0),
                        limiting_cone_angle=float(cone) if cone is not None else fx.LightSpec().limiting_cone_angle)


def _lighting_color(prim: Node, space: str) -> tuple[float, float, float]:
    color = style_color(prim, "lighting-color") or Color(1, 1, 1, 1)
    return _color_in(color, space)[:3]


def _scaled_light(light: fx.LightSpec, scale: tuple[float, float]) -> fx.LightSpec:
    sx, sy = scale
    if light.kind == "distant" or scale == (1.0, 1.0):
        return light
    sz = (sx + sy) / 2.0
    return replace(light, position=(light.position[0] * sx, light.position[1] * sy, light.position[2] * sz),
                   points_at=(light.points_at[0] * sx, light.points_at[1] * sy, light.points_at[2] * sz))


def diffuse(ctx, prim, space, rect):
    light = _light(ctx, prim)
    if light is None:
        return None
    color = _lighting_color(prim, space)
    return _at_kernel_scale(ctx.input(prim.get("in"), space).image, _kernel_unit(ctx, prim),
                            lambda img, k: fx.diffuse_lighting(img, _num(prim, "surfaceScale", 1.0),
                                                               _num(prim, "diffuseConstant", 1.0),
                                                               _scaled_light(light, k), color))


def specular(ctx, prim, space, rect):
    light = _light(ctx, prim)
    if light is None:
        return None
    color = _lighting_color(prim, space)
    return _at_kernel_scale(ctx.input(prim.get("in"), space).image, _kernel_unit(ctx, prim),
                            lambda img, k: fx.specular_lighting(img, _num(prim, "surfaceScale", 1.0),
                                                                _num(prim, "specularConstant", 1.0),
                                                                _num(prim, "specularExponent", 1.0),
                                                                _scaled_light(light, k), color))


def drop_shadow(ctx, prim, space, rect):
    src = ctx.input(prim.get("in"), space).image
    sx, sy = _pair(prim, "stdDeviation", 2.0)
    shadow = fx.gaussian_blur(src, ctx.px(sx, "x"), ctx.px(sy, "y"))
    dx, dy = ctx.vector(_num(prim, "dx", 2.0), _num(prim, "dy", 2.0))
    shadow = fx.offset(shadow, dx, dy)
    color = style_color(prim, "flood-color", "flood-opacity") or Color(0, 0, 0, 1)
    h, w = ctx.shape
    tinted = fx.composite(fx.flood(h, w, _premul(_color_in(color, space))), shadow, "in")
    return fx.merge([tinted, src])


HANDLERS = {
    "feGaussianBlur": blur,
    "feOffset": offset,
    "feFlood": flood,
    "feBlend": blend,
    "feComposite": composite,
    "feColorMatrix": color_matrix,
    "feComponentTransfer": component_transfer,
    "feMorphology": morphology,
    "feConvolveMatrix": convolve,
    "feTile": tile,
    "feMerge": merge,
    "feTurbulence": turbulence,
    "feDisplacementMap": displacement,
    "feDiffuseLighting": diffuse,
    "feSpecularLighting": specular,
    "feDropShadow": drop_shadow,
    "feImage": fe_image,
}
