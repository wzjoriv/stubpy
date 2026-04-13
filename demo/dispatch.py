# demo/dispatch.py
# Exercises advanced stub-generation features:
#   - method → function → method chains (**kwargs through a dispatcher)
#   - Property MRO: subclass overrides only the getter, parent has the setter
#   - Cross-file **kwargs forwarding (make_color imported from demo.functions)
#   - Docstring-only type hints (no annotations, types from NumPy docstring)
from __future__ import annotations

from demo import types
from demo.element import Element
from demo.functions import make_color

__all__ = [
    "Renderer",
    "SVGRenderer",
    "PNGRenderer",
    "ColoredMixin",
    "ColoredSVGRenderer",
    "CrossFileRenderer",
    "save_element",
    "DocstringOnlyFunc",
]


# ---------------------------------------------------------------------------
# Module-level dispatch: save_element → save_svg or save_png
# ---------------------------------------------------------------------------

def save_svg(
    element: Element,
    path: str,
    *,
    width: int = 800,
    height: int = 600,
    compress: bool = False,
) -> int:
    """Write *element* as SVG to *path*. Returns bytes written."""
    content = element.render()
    return len(content.encode())


def save_png(
    element: Element,
    path: str,
    *,
    width: int = 800,
    height: int = 600,
    dpi: int = 96,
) -> int:
    """Write *element* as PNG to *path*. Returns bytes written."""
    return 0


def save_element(element: Element, path: str, fmt: str = "svg", **kwargs) -> int:
    """Save *element* to *path* in the given *fmt*.

    Forwards ``**kwargs`` to :func:`save_svg` (adds *compress*) or
    :func:`save_png` (adds *dpi*) depending on *fmt*.
    Both share *width* and *height*.
    """
    if fmt == "svg":
        return save_svg(element, path, **kwargs)
    return save_png(element, path, **kwargs)


# ---------------------------------------------------------------------------
# Property MRO: base defines getter + setter, child redefines only getter
# ---------------------------------------------------------------------------

class ColoredMixin:
    """Mixin that tracks a fill colour via a property with getter + setter."""

    def __init__(self, color: str = "black") -> None:
        self._color = color

    @property
    def color(self) -> str:
        """The fill colour string."""
        return self._color

    @color.setter
    def color(self, value: str) -> None:
        self._color = value


class ColoredSVGRenderer(ColoredMixin):
    """Overrides the getter only — setter is inherited via Property MRO.

    The stub must still emit ``@color.setter`` even though it is not
    defined directly on this class.
    """

    @property
    def color(self) -> str:
        """The fill colour (overridden to add docstring)."""
        return super().color


# ---------------------------------------------------------------------------
# Method → function chain: Renderer.save dispatches to format-specific savers
# ---------------------------------------------------------------------------

class Renderer:
    """Base renderer.  :meth:`save` routes to format-specific functions.

    .. note::

        ``Renderer.save`` and ``SVGRenderer.save`` forward ``**kwargs`` to
        functions whose first params (``element``, ``path``) are already
        positionally bound in the call.  stubpy currently cannot detect
        positionally-bound arguments and will include them in the expanded
        stub.  This is a known limitation — document or use explicit params
        to avoid it (see ``CrossFileRenderer.tint`` for a clean pattern).
    """

    def __init__(self, element: Element, width: int = 800, height: int = 600) -> None:
        self._element = element
        self._width = width
        self._height = height

    def save(self, path: str, fmt: str = "svg", **kwargs) -> int:
        """Save to *path*; forwards ``**kwargs`` to :func:`save_element`."""
        return save_element(self._element, path, fmt=fmt, **kwargs)

    def render(self) -> str:
        """Return a rendered string."""
        return self._element.render()


class SVGRenderer(Renderer):
    """SVG-only renderer: ``**kwargs`` → :func:`save_svg` (*compress* added)."""

    def save(self, path: str, **kwargs) -> int:
        """Always saves as SVG; forwards ``**kwargs`` to :func:`save_svg`."""
        return save_svg(self._element, path, **kwargs)


class PNGRenderer(Renderer):
    """PNG-only renderer: ``**kwargs`` → :func:`save_png` (*dpi* added)."""

    def save(self, path: str, **kwargs) -> int:
        """Always saves as PNG; forwards ``**kwargs`` to :func:`save_png`."""
        return save_png(self._element, path, **kwargs)


# ---------------------------------------------------------------------------
# Cross-file chain: method forwards **kwargs to make_color from demo.functions
# ---------------------------------------------------------------------------

class CrossFileRenderer:
    """Demonstrates cross-file ``**kwargs`` forwarding.

    :meth:`tint` forwards ``**kwargs`` across the file boundary to
    :func:`demo.functions.make_color`, which is defined in another module.
    The generated stub must expand ``r, g, b, a`` even though that
    information comes from a different source file.
    """

    def tint(self, **kwargs) -> types.Color:
        """Forward to :func:`~demo.functions.make_color` — cross-file chain."""
        return make_color(**kwargs)


# ---------------------------------------------------------------------------
# Docstring-only types (no annotations, types inferred from NumPy docstring)
# ---------------------------------------------------------------------------

def DocstringOnlyFunc(x, y, z=None):
    """A function with types described only in its docstring.

    Parameters
    ----------
    x : int
        An integer value.
    y : str
        A string value.
    z : float, optional
        An optional float.

    Returns
    -------
    bool
        Whether the operation succeeded.
    """
    return True
