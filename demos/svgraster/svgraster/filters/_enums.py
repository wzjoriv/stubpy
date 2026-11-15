"""Enumerations shared by the filter primitives (mirrors of the pybind11 enums)."""
from __future__ import annotations

from enum import IntEnum


class BlendMode(IntEnum):
    """feBlend modes (SVG 1.1 plus the Compositing and Blending set)."""

    NORMAL = 0
    MULTIPLY = 1
    SCREEN = 2
    DARKEN = 3
    LIGHTEN = 4
    OVERLAY = 5
    COLOR_DODGE = 6
    COLOR_BURN = 7
    HARD_LIGHT = 8
    SOFT_LIGHT = 9
    DIFFERENCE = 10
    EXCLUSION = 11
    HUE = 12
    SATURATION = 13
    COLOR = 14
    LUMINOSITY = 15


class CompositeOperator(IntEnum):
    """feComposite operators."""

    OVER = 0
    IN = 1
    OUT = 2
    ATOP = 3
    XOR = 4
    ARITHMETIC = 5
    LIGHTER = 6


class ColorMatrixType(IntEnum):
    """feColorMatrix ``type`` values."""

    MATRIX = 0
    SATURATE = 1
    HUE_ROTATE = 2
    LUMINANCE_TO_ALPHA = 3


class TransferType(IntEnum):
    """feComponentTransfer function types."""

    IDENTITY = 0
    TABLE = 1
    DISCRETE = 2
    LINEAR = 3
    GAMMA = 4


class EdgeMode(IntEnum):
    """feConvolveMatrix edge handling."""

    DUPLICATE = 0
    WRAP = 1
    NONE = 2


class MorphologyOperator(IntEnum):
    """feMorphology operators."""

    ERODE = 0
    DILATE = 1


class Channel(IntEnum):
    """Channel selectors for feDisplacementMap."""

    R = 0
    G = 1
    B = 2
    A = 3


class LightType(IntEnum):
    """Light source kinds for the lighting filters."""

    DISTANT = 0
    POINT = 1
    SPOT = 2


def keyword_to_member(enum_type, keyword: str):
    """Map an SVG keyword such as ``"color-dodge"`` to an enum member."""
    return enum_type[keyword.replace("-", "_").replace("Rotate", "_rotate").replace("To", "_to_").upper()]
