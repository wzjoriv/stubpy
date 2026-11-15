"""feDiffuseLighting and feSpecularLighting (numpy fallbacks)."""
from __future__ import annotations

import math

import numpy as np

from ._enums import LightType

SOBEL_SCALE = 0.25
PIXEL_CENTER = 0.5
NO_CONE = float("nan")


class PyLightSource:
    """Pure-Python stand-in for ``svgraster._filters.LightSource``.

    ``(azimuth, elevation)`` is distant, ``(x, y, z)`` is a point light and
    ``(x, y, z, px, py, pz, specular_exponent=1, limiting_cone_angle=nan)`` a spot light.
    """

    def __init__(self, *args, specular_exponent: float = 1.0, limiting_cone_angle: float = NO_CONE):
        self.position = (0.0, 0.0, 0.0)
        self.points_at = (0.0, 0.0, 0.0)
        self.azimuth = self.elevation = 0.0
        self.specular_exponent = float(specular_exponent)
        self.limiting_cone_angle = float(limiting_cone_angle)
        if len(args) == 2:
            self.kind = LightType.DISTANT
            self.azimuth, self.elevation = float(args[0]), float(args[1])
        elif len(args) == 3:
            self.kind = LightType.POINT
            self.position = tuple(float(a) for a in args)
        elif 6 <= len(args) <= 8:
            self.kind = LightType.SPOT
            self.position = tuple(float(a) for a in args[:3])
            self.points_at = tuple(float(a) for a in args[3:6])
            if len(args) > 6:
                self.specular_exponent = float(args[6])
            if len(args) > 7:
                self.limiting_cone_angle = float(args[7])
        else:
            raise TypeError("unsupported LightSource arguments")


def surface_normals(alpha: np.ndarray, surface_scale: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unit surface normals from the alpha height map (edge pixels replicated)."""
    a = np.pad(alpha.astype(np.float64), 1, mode="edge")
    nx = -surface_scale * SOBEL_SCALE * (
        (a[:-2, 2:] + 2 * a[1:-1, 2:] + a[2:, 2:]) - (a[:-2, :-2] + 2 * a[1:-1, :-2] + a[2:, :-2]))
    ny = -surface_scale * SOBEL_SCALE * (
        (a[2:, :-2] + 2 * a[2:, 1:-1] + a[2:, 2:]) - (a[:-2, :-2] + 2 * a[:-2, 1:-1] + a[:-2, 2:]))
    norm = np.sqrt(nx * nx + ny * ny + 1.0)
    return nx / norm, ny / norm, 1.0 / norm


def light_vectors(light, alpha: np.ndarray, surface_scale: float, color):
    """Unit vectors towards the light and the per-pixel light color."""
    h, w = alpha.shape
    color = np.asarray(color, dtype=np.float64)
    if light.kind == LightType.DISTANT:
        az, el = math.radians(light.azimuth), math.radians(light.elevation)
        vec = (math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el))
        lx, ly, lz = (np.full((h, w), v) for v in vec)
        return lx, ly, lz, np.broadcast_to(color, (h, w, 3))
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    px, py, pz = light.position
    lx, ly = px - (xs + PIXEL_CENTER), py - (ys + PIXEL_CENTER)
    lz = pz - surface_scale * alpha.astype(np.float64)
    norm = np.sqrt(lx * lx + ly * ly + lz * lz)
    norm = np.where(norm > 0, norm, 1.0)
    lx, ly, lz = lx / norm, ly / norm, lz / norm
    if light.kind == LightType.POINT:
        return lx, ly, lz, np.broadcast_to(color, (h, w, 3))
    sx, sy, sz = (b - a for a, b in zip(light.position, light.points_at))
    snorm = math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0
    sx, sy, sz = sx / snorm, sy / snorm, sz / snorm
    minus_ls = -(lx * sx + ly * sy + lz * sz)
    factor = np.power(np.maximum(minus_ls, 0.0), light.specular_exponent)
    if not math.isnan(light.limiting_cone_angle):
        cone = math.cos(math.radians(abs(light.limiting_cone_angle)))
        factor = np.where(minus_ls < cone, 0.0, factor)
    return lx, ly, lz, color * factor[..., None]


def py_diffuse_lighting(img: np.ndarray, surface_scale: float, diffuse_constant: float, light,
                        color=(1.0, 1.0, 1.0)) -> np.ndarray:
    """Opaque diffuse-lit image from the alpha height map."""
    alpha = img[..., 3]
    nx, ny, nz = surface_normals(alpha, surface_scale)
    lx, ly, lz, lc = light_vectors(light, alpha, surface_scale, color)
    ndotl = np.maximum(nx * lx + ny * ly + nz * lz, 0.0)
    rgb = np.clip(diffuse_constant * ndotl[..., None] * lc, 0.0, 1.0)
    out = np.concatenate([rgb, np.ones(alpha.shape + (1,))], axis=-1)
    return out.astype(np.float32)


def py_specular_lighting(img: np.ndarray, surface_scale: float, specular_constant: float,
                         specular_exponent: float, light, color=(1.0, 1.0, 1.0)) -> np.ndarray:
    """Specular highlights with alpha equal to the brightest channel."""
    alpha = img[..., 3]
    nx, ny, nz = surface_normals(alpha, surface_scale)
    lx, ly, lz, lc = light_vectors(light, alpha, surface_scale, color)
    hx, hy, hz = lx, ly, lz + 1.0
    hn = np.sqrt(hx * hx + hy * hy + hz * hz)
    hn = np.where(hn > 0, hn, 1.0)
    ndoth = np.maximum((nx * hx + ny * hy + nz * hz) / hn, 0.0)
    rgb = np.clip(specular_constant * np.power(ndoth, specular_exponent)[..., None] * lc, 0.0, 1.0)
    out = np.concatenate([rgb, rgb.max(axis=-1, keepdims=True)], axis=-1)
    return out.astype(np.float32)
