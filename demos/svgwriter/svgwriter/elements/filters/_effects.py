"""Pixel-effect primitives: color matrix, convolution, blur, morphology,
displacement and turbulence."""

from __future__ import annotations

import enum
from collections.abc import Sequence
from typing import Any, Final

from ..._internal._typing import Self
from .base import FilterPrimitive, SingleInput, TwoInputs

__all__ = [
    "Channel",
    "ColorMatrixType",
    "EdgeMode",
    "FeColorMatrix",
    "FeConvolveMatrix",
    "FeDisplacementMap",
    "FeGaussianBlur",
    "FeMorphology",
    "FeTurbulence",
    "MorphologyOperator",
    "TurbulenceType",
]

COLOR_MATRIX_SIZE: Final = 20
LUMA_RED: Final = 0.2126
LUMA_GREEN: Final = 0.7152
LUMA_BLUE: Final = 0.0722


class ColorMatrixType(str, enum.Enum):
    MATRIX = "matrix"
    SATURATE = "saturate"
    HUE_ROTATE = "hueRotate"
    LUMINANCE_TO_ALPHA = "luminanceToAlpha"


class EdgeMode(str, enum.Enum):
    DUPLICATE = "duplicate"
    WRAP = "wrap"
    NONE = "none"


class Channel(str, enum.Enum):
    R = "R"
    G = "G"
    B = "B"
    A = "A"
    RED = "R"
    GREEN = "G"
    BLUE = "B"
    ALPHA = "A"


class MorphologyOperator(str, enum.Enum):
    ERODE = "erode"
    DILATE = "dilate"


class TurbulenceType(str, enum.Enum):
    FRACTAL_NOISE = "fractalNoise"
    TURBULENCE = "turbulence"


class FeColorMatrix(SingleInput, tag="feColorMatrix"):
    """``<feColorMatrix>``: a 5x4 color transform or a shorthand.

    Examples
    --------
    >>> FeColorMatrix.saturate(0).get("values")
    0
    """

    def __init__(
        self,
        type: ColorMatrixType = ColorMatrixType.MATRIX,
        values: Sequence[float] | float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if type is ColorMatrixType.MATRIX and isinstance(values, (list, tuple)) and len(values) != COLOR_MATRIX_SIZE:
            raise ValueError(f"a color matrix needs {COLOR_MATRIX_SIZE} values")
        self.update(type=type, values=tuple(values) if isinstance(values, (list, tuple)) else values)

    @classmethod
    def saturate(cls, amount: float, **kwargs: Any) -> Self:
        return cls(ColorMatrixType.SATURATE, amount, **kwargs)

    @classmethod
    def hue_rotate(cls, degrees: float, **kwargs: Any) -> Self:
        return cls(ColorMatrixType.HUE_ROTATE, degrees, **kwargs)

    @classmethod
    def luminance_to_alpha(cls, **kwargs: Any) -> Self:
        return cls(ColorMatrixType.LUMINANCE_TO_ALPHA, **kwargs)

    @classmethod
    def grayscale(cls, **kwargs: Any) -> Self:
        row = (LUMA_RED, LUMA_GREEN, LUMA_BLUE, 0.0, 0.0)
        return cls(values=row * 3 + (0.0, 0.0, 0.0, 1.0, 0.0), **kwargs)


class FeConvolveMatrix(SingleInput, tag="feConvolveMatrix"):
    """``<feConvolveMatrix>``: apply a convolution kernel."""

    def __init__(
        self,
        kernel_matrix: Sequence[float] = (),
        order: int | tuple[int, int] = 3,
        *,
        divisor: float | None = None,
        bias: float | None = None,
        target_x: int | None = None,
        target_y: int | None = None,
        edge_mode: EdgeMode | None = None,
        kernel_unit_length: float | tuple[float, float] | None = None,
        preserve_alpha: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        columns, rows = (order, order) if isinstance(order, int) else order
        if kernel_matrix and len(kernel_matrix) != columns * rows:
            raise ValueError(f"kernel needs {columns * rows} values, got {len(kernel_matrix)}")
        self.update(
            order=order,
            kernel_matrix=tuple(kernel_matrix) or None,
            divisor=divisor,
            bias=bias,
            target_x=target_x,
            target_y=target_y,
            edge_mode=edge_mode,
            kernel_unit_length=kernel_unit_length,
            preserve_alpha=preserve_alpha,
        )


class FeGaussianBlur(SingleInput, tag="feGaussianBlur"):
    """``<feGaussianBlur>``."""

    def __init__(self, std_deviation: float | tuple[float, float] = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(std_deviation=std_deviation)


class FeMorphology(SingleInput, tag="feMorphology"):
    """``<feMorphology>``: erode (thin) or dilate (fatten) the input."""

    def __init__(
        self,
        operator: MorphologyOperator = MorphologyOperator.ERODE,
        radius: float | tuple[float, float] = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(operator=operator, radius=radius)


class FeDisplacementMap(TwoInputs, tag="feDisplacementMap"):
    """``<feDisplacementMap>``: displace ``in`` by channels of ``in2``."""

    def __init__(
        self,
        scale: float = 0,
        x_channel_selector: Channel = Channel.A,
        y_channel_selector: Channel = Channel.A,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(scale=scale, x_channel_selector=x_channel_selector, y_channel_selector=y_channel_selector)


class FeTurbulence(FilterPrimitive, tag="feTurbulence"):
    """``<feTurbulence>``: Perlin noise."""

    def __init__(
        self,
        base_frequency: float | tuple[float, float] = 0,
        num_octaves: int = 1,
        *,
        seed: float | None = None,
        stitch_tiles: bool = False,
        type: TurbulenceType = TurbulenceType.TURBULENCE,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(
            base_frequency=base_frequency,
            num_octaves=num_octaves,
            seed=seed,
            stitch_tiles="stitch" if stitch_tiles else None,
            type=type,
        )
