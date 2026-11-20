"""Lowercase aliases for every element class.

``svg.circle`` is ``svg.Circle``, ``svg.linear_gradient`` is
``svg.LinearGradient`` and so on.

``filter`` and ``set`` shadow builtins, so they are attributes of the
package but left out of ``__all__``. ``svgwriter.path`` names the class,
not the ``svgwriter.path`` sub-package; import from that with
``from svgwriter.path import PathBuilder``.
"""

from __future__ import annotations

from .elements import (
    Animate,
    Circle,
    Defs,
    FeGaussianBlur,
    Filter,
    Group,
    Line,
    LinearGradient,
    Path,
    Rect,
    Set,
    Stop,
    Svg,
    Use,
)

__all__ = [
    "animate",
    "circle",
    "defs",
    "fe_gaussian_blur",
    "group",
    "line",
    "linear_gradient",
    "path",
    "rect",
    "stop",
    "svg",
    "use",
]

animate = Animate
circle = Circle
defs = Defs
fe_gaussian_blur = FeGaussianBlur
filter = Filter
group = Group
line = Line
linear_gradient = LinearGradient
path = Path
rect = Rect
set = Set
stop = Stop
svg = Svg
use = Use
