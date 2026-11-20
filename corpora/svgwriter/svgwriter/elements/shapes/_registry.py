"""Create shapes by name: ``make_shape("circle", r=5)``."""

from __future__ import annotations

from typing import Any, Literal

from ._basic import Circle, Line, Rect, Shape

__all__ = ["REGISTRY", "ShapeFactory", "make_shape"]

REGISTRY: dict[str, type[Shape]] = {"circle": Circle, "rect": Rect, "line": Line}


def make_shape(kind: Literal["circle", "rect", "line"], **kwargs: Any) -> Shape:
    """Build the shape registered under *kind*.

    Parameters
    ----------
    kind : {"circle", "rect", "line"}
        A key of :data:`REGISTRY`.
    **kwargs
        Passed to the shape's constructor.

    Returns
    -------
    Shape
        The new shape.

    Examples
    --------
    >>> make_shape("circle", r=5).tag
    'circle'
    """
    return REGISTRY[kind](**kwargs)


class ShapeFactory:
    """Builds shapes from a registry of names."""

    registry: dict[str, type[Shape]] = REGISTRY

    @classmethod
    def build(cls, kind: str, **kwargs: Any) -> Shape:
        """Build the shape registered under *kind*.

        Parameters
        ----------
        kind : str
            A key of :attr:`registry`.
        **kwargs
            Passed to the shape's constructor.

        Returns
        -------
        Shape
            The new shape.

        Examples
        --------
        >>> ShapeFactory.build("rect", width=2, height=3).tag
        'rect'
        """
        return cls.registry[kind](**kwargs)
