"""``viewBox`` and ``preserveAspectRatio`` handling."""
from __future__ import annotations

from typing import NamedTuple

from ..dom.transform import Matrix
from ..dom.units import parse_numbers

_ALIGN_FACTORS = {"min": 0.0, "mid": 0.5, "max": 1.0}


class ViewBox(NamedTuple):
    """A ``viewBox`` rectangle."""

    x: float
    y: float
    width: float
    height: float


class AspectRatio(NamedTuple):
    """A parsed ``preserveAspectRatio``."""

    align_x: float | None = 0.5
    align_y: float | None = 0.5
    slice: bool = False

    @property
    def is_none(self) -> bool:
        """Whether non-uniform scaling is allowed."""
        return self.align_x is None


def parse_viewbox(text: str | None) -> ViewBox | None:
    """Parse ``viewBox``; ``None`` if absent or invalid."""
    nums = parse_numbers(text)
    if len(nums) != 4 or nums[2] <= 0 or nums[3] <= 0:
        return None
    return ViewBox(*nums)


def parse_aspect_ratio(text: str | None) -> AspectRatio:
    """Parse ``preserveAspectRatio`` (``defer`` is ignored)."""
    tokens = (text or "").split()
    if tokens and tokens[0] == "defer":
        tokens = tokens[1:]
    if not tokens:
        return AspectRatio()
    align = tokens[0]
    slice_ = len(tokens) > 1 and tokens[1] == "slice"
    if align == "none":
        return AspectRatio(None, None, False)
    if len(align) == 8 and align[0] == "x" and align[4] == "Y":
        ax = _ALIGN_FACTORS.get(align[1:4].lower())
        ay = _ALIGN_FACTORS.get(align[5:8].lower())
        if ax is not None and ay is not None:
            return AspectRatio(ax, ay, slice_)
    return AspectRatio()


def viewbox_transform(box: ViewBox, width: float, height: float,
                      aspect: AspectRatio = AspectRatio()) -> Matrix:
    """Map ``box`` into a ``width x height`` viewport."""
    sx, sy = width / box.width, height / box.height
    if aspect.is_none:
        return Matrix(sx, 0.0, 0.0, sy, -box.x * sx, -box.y * sy)
    scale = max(sx, sy) if aspect.slice else min(sx, sy)
    tx = (width - box.width * scale) * aspect.align_x - box.x * scale
    ty = (height - box.height * scale) * aspect.align_y - box.y * scale
    return Matrix(scale, 0.0, 0.0, scale, tx, ty)
