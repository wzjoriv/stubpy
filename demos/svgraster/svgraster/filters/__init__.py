"""SVG filter primitives on premultiplied float32 RGBA arrays.

Each function dispatches to the pybind11 module ``svgraster._filters`` when it
is built and falls back to numpy otherwise.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .. import _backend
from ..raster.sample import py_sample_image
from ._basic import gaussian_kernel, py_flood, py_gaussian_blur, py_merge, py_offset, py_tile
from ._blend import py_blend, py_composite
from ._color import PyTransferFunction, color_matrix_values, py_color_matrix, py_component_transfer
from ._enums import (
    BlendMode,
    Channel,
    ColorMatrixType,
    CompositeOperator,
    EdgeMode,
    LightType,
    MorphologyOperator,
    ResampleFilter,
    TransferType,
    keyword_to_member,
)
from ._lighting import NO_CONE, PyLightSource, py_diffuse_lighting, py_specular_lighting
from ._noise import py_turbulence
from ._spatial import py_convolve_matrix, py_displacement_map, py_morphology


@dataclass
class TransferSpec:
    """One feFuncX element."""

    kind: str = "identity"
    table: list[float] = field(default_factory=list)
    slope: float = 1.0
    intercept: float = 0.0
    amplitude: float = 1.0
    exponent: float = 1.0
    offset: float = 0.0


@dataclass
class LightSpec:
    """A light source in the filter's pixel space."""

    kind: str = "distant"
    azimuth: float = 0.0
    elevation: float = 0.0
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    points_at: tuple[float, float, float] = (0.0, 0.0, 0.0)
    specular_exponent: float = 1.0
    limiting_cone_angle: float = NO_CONE


def _f32(img: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(img, dtype=np.float32)


def _enum(native, enum_type, keyword: str):
    member = keyword_to_member(enum_type, keyword) if isinstance(keyword, str) else enum_type(keyword)
    return getattr(getattr(native, enum_type.__name__), member.name) if native is not None else member


def _transfer(spec: TransferSpec, native):
    cls = native.TransferFunction if native is not None else PyTransferFunction
    kind = keyword_to_member(TransferType, spec.kind)
    if kind in (TransferType.TABLE, TransferType.DISCRETE):
        return cls(_enum(native, TransferType, kind), [float(v) for v in spec.table])
    if kind == TransferType.LINEAR:
        return cls(spec.slope, spec.intercept)
    if kind == TransferType.GAMMA:
        return cls(spec.amplitude, spec.exponent, spec.offset)
    return cls()


def _light(spec: LightSpec, native):
    cls = native.LightSource if native is not None else PyLightSource
    if spec.kind == "distant":
        return cls(spec.azimuth, spec.elevation)
    if spec.kind == "point":
        return cls(*spec.position)
    return cls(*spec.position, *spec.points_at, specular_exponent=spec.specular_exponent,
               limiting_cone_angle=spec.limiting_cone_angle)


def gaussian_blur(img: np.ndarray, sx: float, sy: float | None = None) -> np.ndarray:
    """feGaussianBlur."""
    native = _backend.native("filters")
    if native is None:
        return py_gaussian_blur(img, sx, sy)
    return native.gaussian_blur(_f32(img), sx) if sy is None else native.gaussian_blur(_f32(img), sx, sy)


def offset(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """feOffset with bilinear sub-pixel shifts."""
    native = _backend.native("filters")
    return native.offset(_f32(img), dx, dy) if native is not None else py_offset(img, dx, dy)


def py_resample(img: np.ndarray, height: int, width: int, filter: int = ResampleFilter.BILINEAR) -> np.ndarray:
    """Resize so pixel centres map onto each other (numpy fallback)."""
    if height <= 0 or width <= 0:
        raise ValueError("size must be positive")
    h, w = img.shape[:2]
    out = np.zeros((height, width, 4), dtype=np.float32)
    inv = np.array([[w / width, 0.0, 0.0], [0.0, h / height, 0.0]])
    py_sample_image(out, img, inv, bilinear=ResampleFilter(filter) == ResampleFilter.BILINEAR)
    return out


def resample(img: np.ndarray, height: int, width: int, filter: str = "bilinear") -> np.ndarray:
    """Resize an image (used for ``filterRes`` and ``kernelUnitLength``)."""
    native = _backend.native("filters")
    code = _enum(native, ResampleFilter, filter)
    if native is not None:
        return native.resample(_f32(img), int(height), int(width), filter=code)
    return py_resample(img, int(height), int(width), code)


def flood(height: int, width: int, color: Sequence[float]) -> np.ndarray:
    """feFlood with a premultiplied color."""
    native = _backend.native("filters")
    color = tuple(float(c) for c in color)
    return native.flood(height, width, color) if native is not None else py_flood(height, width, color)


def blend(src: np.ndarray, backdrop: np.ndarray, mode: str = "normal") -> np.ndarray:
    """feBlend of ``in`` over ``in2``."""
    native = _backend.native("filters")
    code = _enum(native, BlendMode, mode)
    return native.blend(_f32(src), _f32(backdrop), code) if native is not None else py_blend(src, backdrop, code)


def composite(a: np.ndarray, b: np.ndarray, operator: str = "over",
              k: Sequence[float] = (0.0, 0.0, 0.0, 0.0)) -> np.ndarray:
    """feComposite of ``in`` with ``in2``."""
    native = _backend.native("filters")
    code = _enum(native, CompositeOperator, operator)
    if native is not None:
        return native.composite(_f32(a), _f32(b), code, *k)
    return py_composite(a, b, code, *k)


def color_matrix(img: np.ndarray, kind: str = "matrix", values: Sequence[float] = ()) -> np.ndarray:
    """feColorMatrix."""
    native = _backend.native("filters")
    code = _enum(native, ColorMatrixType, kind)
    values = [float(v) for v in values]
    return native.color_matrix(_f32(img), code, values) if native is not None else py_color_matrix(img, code, values)


def component_transfer(img: np.ndarray, funcs: Sequence[TransferSpec | None]) -> np.ndarray:
    """feComponentTransfer with up to four channel functions (R, G, B, A)."""
    native = _backend.native("filters")
    objs = [_transfer(spec or TransferSpec(), native) for spec in funcs]
    if native is not None:
        return native.component_transfer(_f32(img), objs)
    return py_component_transfer(img, objs)


def morphology(img: np.ndarray, rx: int, ry: int, operator: str = "erode") -> np.ndarray:
    """feMorphology."""
    native = _backend.native("filters")
    code = _enum(native, MorphologyOperator, operator)
    return native.morphology(_f32(img), rx, ry, code) if native is not None else py_morphology(img, rx, ry, code)


def convolve_matrix(img: np.ndarray, kernel: np.ndarray, divisor: float | None = None, bias: float = 0.0,
                    target: tuple[int, int] = (-1, -1), edge_mode: str = "duplicate",
                    preserve_alpha: bool = False) -> np.ndarray:
    """feConvolveMatrix; ``divisor`` defaults to the kernel sum (or 1)."""
    native = _backend.native("filters")
    kernel = np.ascontiguousarray(kernel, dtype=np.float64)
    if divisor is None or divisor == 0:
        divisor = float(kernel.sum()) or 1.0
    code = _enum(native, EdgeMode, edge_mode)
    args = (divisor, bias, target[0], target[1], code, preserve_alpha)
    if native is not None:
        return native.convolve_matrix(_f32(img), kernel, *args)
    return py_convolve_matrix(img, kernel, *args)


def tile(img: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    """feTile from the pixel rectangle ``(x, y, w, h)`` of the input."""
    native = _backend.native("filters")
    return native.tile(_f32(img), *rect) if native is not None else py_tile(img, *rect)


def merge(layers: Sequence[np.ndarray]) -> np.ndarray:
    """feMerge."""
    native = _backend.native("filters")
    return native.merge([_f32(x) for x in layers]) if native is not None else py_merge(layers)


def turbulence(height: int, width: int, inv: np.ndarray, base_frequency: tuple[float, float],
               octaves: int = 1, seed: int = 0, stitch: bool = False, fractal: bool = False,
               tile_rect: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)) -> np.ndarray:
    """feTurbulence; ``inv`` maps pixel coordinates to filter user space."""
    native = _backend.native("filters")
    inv = np.ascontiguousarray(inv, dtype=np.float64)
    args = (height, width, inv, float(base_frequency[0]), float(base_frequency[1]), int(octaves),
            int(seed), bool(stitch), bool(fractal), tuple(float(v) for v in tile_rect))
    return native.turbulence(*args) if native is not None else py_turbulence(*args)


def displacement_map(img: np.ndarray, displacement: np.ndarray, scale: float,
                     x_channel: str = "A", y_channel: str = "A") -> np.ndarray:
    """feDisplacementMap; ``scale`` is in pixels."""
    native = _backend.native("filters")
    xc, yc = _enum(native, Channel, x_channel), _enum(native, Channel, y_channel)
    if native is not None:
        return native.displacement_map(_f32(img), _f32(displacement), scale, xc, yc)
    return py_displacement_map(img, displacement, scale, xc, yc)


def diffuse_lighting(img: np.ndarray, surface_scale: float, diffuse_constant: float, light: LightSpec,
                     color: Sequence[float] = (1.0, 1.0, 1.0)) -> np.ndarray:
    """feDiffuseLighting."""
    native = _backend.native("filters")
    src = _light(light, native)
    color = tuple(float(c) for c in color[:3])
    if native is not None:
        return native.diffuse_lighting(_f32(img), surface_scale, diffuse_constant, src, color)
    return py_diffuse_lighting(img, surface_scale, diffuse_constant, src, color)


def specular_lighting(img: np.ndarray, surface_scale: float, specular_constant: float,
                      specular_exponent: float, light: LightSpec,
                      color: Sequence[float] = (1.0, 1.0, 1.0)) -> np.ndarray:
    """feSpecularLighting."""
    native = _backend.native("filters")
    src = _light(light, native)
    color = tuple(float(c) for c in color[:3])
    if native is not None:
        return native.specular_lighting(_f32(img), surface_scale, specular_constant, specular_exponent, src, color)
    return py_specular_lighting(img, surface_scale, specular_constant, specular_exponent, src, color)


def blur(img: np.ndarray, std: float, **kwargs) -> np.ndarray:
    """Blur with a single deviation; ``**kwargs`` go to :func:`gaussian_blur`."""
    return gaussian_blur(img, std, **kwargs)


__all__ = [
    "BlendMode",
    "Channel",
    "ColorMatrixType",
    "CompositeOperator",
    "EdgeMode",
    "LightSpec",
    "LightType",
    "MorphologyOperator",
    "ResampleFilter",
    "TransferSpec",
    "TransferType",
    "blend",
    "blur",
    "color_matrix",
    "color_matrix_values",
    "component_transfer",
    "composite",
    "convolve_matrix",
    "diffuse_lighting",
    "displacement_map",
    "flood",
    "gaussian_blur",
    "gaussian_kernel",
    "merge",
    "morphology",
    "offset",
    "resample",
    "specular_lighting",
    "tile",
    "turbulence",
]
