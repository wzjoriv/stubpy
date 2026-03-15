# demo/element.py
# Base element class — imported by other demo files to test cross-file resolution.
from __future__ import annotations

from typing import Any, Dict, List, Optional
from demo import types

class Style:
    """Inline style bag — maps CSS-like property names to values."""

    def __init__(self, **props: Any) -> None:
        self._data: Dict[str, Any] = dict(props)

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def render(self) -> str:
        return "; ".join(f"{k}: {v}" for k, v in self._data.items())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Style:
        return cls(**data)


class Element:
    """
    Base class for all drawable elements.
    Provides id, title, opacity and a Style object.
    Every subclass passes extra params up via **kwargs.
    """

    def __init__(
        self,
        id: Optional[str] = None,
        title: Optional[str] = None,
        opacity: float = 1.0,
    ) -> None:
        self.id      = id
        self.title   = title
        self.opacity = opacity
        self.style   = Style()

    # ── transform helpers (chainable) ───────────────────────────────────────

    def translate(self, tx: float, ty: float = 0.0) -> Element:
        return self

    def rotate(
        self,
        angle: float,
        cx: Optional[float] = None,
        cy: Optional[float] = None,
    ) -> Element:
        return self

    def scale(self, sx: float, sy: Optional[float] = None) -> Element:
        return self

    # ── style helpers ────────────────────────────────────────────────────────

    def apply(self, **props: Any) -> Element:
        for k, v in props.items():
            self.style[k] = v
        return self

    # ── rendering ────────────────────────────────────────────────────────────

    def render(self, compact: bool = False) -> str:
        return ""

    def __repr__(self) -> str:
        return self.render()

    # ── factory classmethods ─────────────────────────────────────────────────

    @classmethod
    def blank(cls, **kwargs) -> Element:
        """Create a transparent (opacity=0) element with all other defaults."""
        return cls(opacity=0.0, **kwargs)