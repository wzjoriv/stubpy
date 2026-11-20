"""Reusable looks for shapes: a style, a saved swatch and a template."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .elements.shapes import Rect

__all__ = ["Style", "Swatch", "Template", "tint"]


def tint(
    element: Rect,
    *,
    fill: str = "#c8ccd4",
    stroke: str = "#2b2f36",
    stroke_width: float = 1.0,
) -> Rect:
    """Apply a fill and stroke to *element*.

    Parameters
    ----------
    element : Rect
        The shape to paint.
    fill : str
        Fill color.
    stroke : str
        Stroke color.
    stroke_width : float
        Stroke width in user units.

    Returns
    -------
    Rect
        *element*, painted.

    Examples
    --------
    >>> tint(Rect(0, 0, 4, 4)).attributes["fill"]
    '#c8ccd4'
    """
    element.update(fill=fill, stroke=stroke, stroke_width=stroke_width)
    return element


@dataclass(frozen=True)
class Style:
    """Fill and stroke colors."""

    fill: str = "#c8ccd4"
    stroke: str = "#2b2f36"

    def variant(self, **changes: Any) -> Style:
        """A copy of this style with *changes* applied.

        Parameters
        ----------
        **changes
            Fields to override.

        Returns
        -------
        Style
            The modified copy.

        Examples
        --------
        >>> Style().variant(fill="#fff").fill
        '#fff'
        """
        return replace(self, **changes)


class Swatch:
    """A rectangle in a style, savable on its own."""

    def __init__(self, style: Style | None = None) -> None:
        self.style = style or Style()

    def save(self, path: str, **kwargs: Any) -> None:
        """Write the swatch to *path*.

        Parameters
        ----------
        path : str
            Destination file.
        **kwargs
            Passed to :func:`open`.
        """
        with open(path, "w", **kwargs) as handle:
            handle.write(f'<rect fill="{self.style.fill}" stroke="{self.style.stroke}"/>')


class Template:
    """Text with a placeholder per call."""

    def body(self, name: str, *, scale: float = 1.0) -> str:
        return f"{name}@{scale}"

    def render(self, *args: Any, **kwargs: Any) -> str:
        """Render the template.

        Parameters
        ----------
        *args, **kwargs
            Passed to :meth:`body`.

        Returns
        -------
        str
            The rendered text.
        """
        return self.body(*args, **kwargs)
