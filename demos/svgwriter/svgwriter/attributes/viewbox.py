"""``viewBox`` and ``preserveAspectRatio``."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Final, NamedTuple

from .._internal._constants import DEFAULT_PRECISION
from .._internal._speedups import format_number

__all__ = ["Align", "MeetOrSlice", "PreserveAspectRatio", "ViewBox"]

_SEPARATORS: Final = re.compile(r"[\s,]+")


class ViewBox(NamedTuple):
    """The ``viewBox`` rectangle in user units."""

    min_x: float
    min_y: float
    width: float
    height: float

    @classmethod
    def parse(cls, text: str) -> ViewBox:
        parts = [p for p in _SEPARATORS.split(text.strip()) if p]
        if len(parts) != 4:
            raise ValueError(f"viewBox needs four numbers: {text!r}")
        box = cls(*(float(p) for p in parts))
        if box.width < 0 or box.height < 0:
            raise ValueError("viewBox width and height must be non-negative")
        return box

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return " ".join(format_number(v, precision) for v in self)


class Align(str, enum.Enum):
    """Alignment values of ``preserveAspectRatio``."""

    NONE = "none"
    X_MIN_Y_MIN = "xMinYMin"
    X_MID_Y_MIN = "xMidYMin"
    X_MAX_Y_MIN = "xMaxYMin"
    X_MIN_Y_MID = "xMinYMid"
    X_MID_Y_MID = "xMidYMid"
    X_MAX_Y_MID = "xMaxYMid"
    X_MIN_Y_MAX = "xMinYMax"
    X_MID_Y_MAX = "xMidYMax"
    X_MAX_Y_MAX = "xMaxYMax"
    CENTER = "xMidYMid"


class MeetOrSlice(str, enum.Enum):
    MEET = "meet"
    SLICE = "slice"


@dataclass(frozen=True)
class PreserveAspectRatio:
    """How a viewBox is fitted into its viewport.

    Parameters
    ----------
    align : Align
        Which point of the viewBox lines up with the viewport.
    meet_or_slice : MeetOrSlice
        Scale to fit entirely (meet) or to cover (slice).
    defer : bool
        Emit the ``defer`` keyword (only meaningful on ``image``).
    """

    align: Align = Align.X_MID_Y_MID
    meet_or_slice: MeetOrSlice = MeetOrSlice.MEET
    defer: bool = False

    @classmethod
    def parse(cls, text: str) -> PreserveAspectRatio:
        words = text.split()
        defer = bool(words) and words[0] == "defer"
        if defer:
            words = words[1:]
        if not words or len(words) > 2:
            raise ValueError(f"invalid preserveAspectRatio: {text!r}")
        mode = MeetOrSlice(words[1]) if len(words) == 2 else MeetOrSlice.MEET
        return cls(Align(words[0]), mode, defer)

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        words = ["defer"] if self.defer else []
        words.append(self.align.value)
        if self.meet_or_slice is not MeetOrSlice.MEET:
            words.append(self.meet_or_slice.value)
        return " ".join(words)

    def __str__(self) -> str:
        return self.svg_value()
