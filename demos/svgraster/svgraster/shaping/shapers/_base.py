"""The default shaper and the per-run plan every shaper fills in."""
from __future__ import annotations

from dataclasses import dataclass, field

COMMON_STAGES: tuple[tuple[bytes, ...], ...] = ((b"ccmp", b"locl"),)
DEFAULT_LIGATURES: tuple[bytes, ...] = (b"rlig", b"rclt", b"calt", b"liga", b"clig")
POSITIONING: tuple[bytes, ...] = (b"kern", b"mark", b"mkmk", b"curs", b"dist", b"abvm", b"blwm")
VERTICAL: tuple[bytes, ...] = (b"vert", b"vrt2")


@dataclass
class Plan:
    """Feature masks for one run; bit 0 is the global mask every glyph carries."""

    masks: dict[bytes, int] = field(default_factory=dict)
    global_mask: int = 1
    next_bit: int = 2

    def mask(self, tag: bytes, global_: bool = True) -> int:
        """The mask bit of ``tag``, allocating one on first use."""
        if tag not in self.masks:
            if global_:
                self.masks[tag] = self.global_mask
            else:
                self.masks[tag] = self.next_bit
                self.next_bit <<= 1
        return self.masks[tag]


class Shaper:
    """The default shaper (Latin, Greek, Cyrillic and every script without its own)."""

    local_features: tuple[bytes, ...] = ()
    zero_marks = True
    fallback_marks = True

    def stages(self, vertical: bool = False) -> list[tuple[bytes, ...]]:
        """GSUB feature stages, applied in order with a pause after each."""
        extra = VERTICAL if vertical else ()
        return [*COMMON_STAGES, DEFAULT_LIGATURES + extra]

    def positioning(self) -> tuple[bytes, ...]:
        """GPOS features."""
        return POSITIONING

    def preprocess(self, cps: list[int]) -> tuple[list[int], list[int]]:
        """Code points to shape and the cluster (input index) of each."""
        return cps, list(range(len(cps)))

    def setup(self, buf, plan: Plan, font) -> None:
        """Assign per-glyph feature masks and reorder before GSUB."""

    def pause(self, stage: int, buf, plan: Plan, font) -> None:
        """Hook run after GSUB stage ``stage``."""
