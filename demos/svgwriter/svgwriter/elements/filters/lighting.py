"""Lighting primitives and light sources."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from ...color.color import Color
from .._mixins import CoreAttributes
from ..base import Category, Child, ContentModel
from .base import SingleInput

__all__ = [
    "FeDiffuseLighting",
    "FeDistantLight",
    "FePointLight",
    "FeSpecularLighting",
    "FeSpotLight",
    "LightSource",
    "Vector3",
]

Vector3 = tuple[float, float, float]


def _normalize(x: float, y: float, z: float) -> Vector3:
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x / length, y / length, z / length)


def _num(element: CoreAttributes, name: str, default: float = 0.0) -> float:
    return float(element.get(name, default))


class LightSource(CoreAttributes, ABC, category=Category.LIGHT_SOURCE, content=ContentModel.ELEMENTS):
    """Abstract light source; the child of a lighting primitive."""

    @property
    @abstractmethod
    def directional(self) -> bool:
        """``True`` when the light direction is the same everywhere."""

    @abstractmethod
    def light_vector(self, x: float, y: float, z: float) -> Vector3:
        """Unit vector from a surface point towards the light."""


class FeDistantLight(LightSource, tag="feDistantLight"):
    """``<feDistantLight>``: light from infinitely far away."""

    def __init__(self, azimuth: float = 0, elevation: float = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(azimuth=azimuth, elevation=elevation)

    @property
    def directional(self) -> bool:
        return True

    def light_vector(self, x: float, y: float, z: float) -> Vector3:
        azimuth = math.radians(_num(self, "azimuth"))
        elevation = math.radians(_num(self, "elevation"))
        return (
            math.cos(azimuth) * math.cos(elevation),
            math.sin(azimuth) * math.cos(elevation),
            math.sin(elevation),
        )


class FePointLight(LightSource, tag="fePointLight"):
    """``<fePointLight>``: an omnidirectional point light."""

    def __init__(self, x: float = 0, y: float = 0, z: float = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(x=x, y=y, z=z)

    @property
    def directional(self) -> bool:
        return False

    def light_vector(self, x: float, y: float, z: float) -> Vector3:
        return _normalize(_num(self, "x") - x, _num(self, "y") - y, _num(self, "z") - z)


class FeSpotLight(FePointLight, tag="feSpotLight"):
    """``<feSpotLight>``: a point light aimed at ``pointsAt``."""

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        z: float = 0,
        *,
        points_at_x: float = 0,
        points_at_y: float = 0,
        points_at_z: float = 0,
        specular_exponent: float | None = None,
        limiting_cone_angle: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(x, y, z, **kwargs)
        self.update(
            points_at_x=points_at_x,
            points_at_y=points_at_y,
            points_at_z=points_at_z,
            specular_exponent=specular_exponent,
            limiting_cone_angle=limiting_cone_angle,
        )


class _Lighting(SingleInput):
    def __init__(
        self,
        *light: Child,
        surface_scale: float | None = None,
        kernel_unit_length: float | tuple[float, float] | None = None,
        lighting_color: Color | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*light, **kwargs)
        self.update(surface_scale=surface_scale, kernel_unit_length=kernel_unit_length, lighting_color=lighting_color)

    @property
    def light(self) -> LightSource | None:
        return next((c for c in self if isinstance(c, LightSource)), None)


class FeDiffuseLighting(_Lighting, tag="feDiffuseLighting"):
    """``<feDiffuseLighting>``: Lambertian lighting of the alpha bump map."""

    def __init__(self, *light: Child, diffuse_constant: float | None = None, **kwargs: Any) -> None:
        super().__init__(*light, **kwargs)
        self.update(diffuse_constant=diffuse_constant)


class FeSpecularLighting(_Lighting, tag="feSpecularLighting"):
    """``<feSpecularLighting>``: Phong specular highlights."""

    def __init__(
        self,
        *light: Child,
        specular_constant: float | None = None,
        specular_exponent: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*light, **kwargs)
        self.update(specular_constant=specular_constant, specular_exponent=specular_exponent)
