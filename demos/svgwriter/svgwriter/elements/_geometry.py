"""``PathOperand``: outlines, path conversion and geometric operators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeAlias, Union

from ..path.data import BBox, PathData
from ..transform.matrix import Matrix, Point
from ..transform.ops import TransformOp
from ..transform.transform import Transform, TransformLike, as_transform
from .base import Element

if TYPE_CHECKING:
    from ..ops.boolean import BooleanOp
    from ..ops.measure import Cap, Join
    from .shapes import Path

__all__ = ["Operand", "PathOperand"]

Operand: TypeAlias = Union["PathOperand", PathData, str]
NOT_COPIED: Final = frozenset({"id", "transform"})
_TRANSFORMS: Final = (Transform, TransformOp, Matrix, str)


class PathOperand(Element):
    """An element with an outline.

    Adds :meth:`to_path`, transforms baked with ``*``/``@`` and, with
    skia-python installed, boolean operators and exact measurement:

    ========  ==============================
    ``a | b`` union
    ``a & b`` intersection
    ``a - b`` difference
    ``a ^ b`` exclusive or
    ``a * t`` bake transform *t* (also ``a @ t``)
    ========  ==============================

    Every operator returns a new :class:`~svgwriter.Path` carrying the
    left operand's presentation attributes.
    """

    geometry_attributes: ClassVar[frozenset[str]] = frozenset()
    """Attributes describing the geometry; not copied by :meth:`to_path`."""

    def local_outline(self) -> PathData:
        """Outline in the element's own coordinates (``transform`` ignored)."""
        raise NotImplementedError(f"<{self.tag}> has no outline")

    def outline(self) -> PathData:
        """Outline with the element's ``transform`` applied."""
        data = self.local_outline()
        raw = self.attributes.get("transform")
        return data if raw is None else data.transformed(as_transform(raw))

    def to_path(self, **kwargs: Any) -> Path:
        """An equivalent ``<path>``; keywords override copied attributes."""
        from .shapes import Path

        path = Path(self.outline())
        path.attributes.update(
            (k, v) for k, v in self.attributes.items() if k not in NOT_COPIED and k not in self.geometry_attributes
        )
        path.update(**kwargs)
        return path

    def _with_data(self, data: PathData) -> Path:
        path = self.to_path()
        path.d = data
        return path

    def _result(self, data: PathData) -> Path:
        path = self._with_data(data)
        path.discard("fill-rule")
        return path

    def transformed(self, transform: TransformLike) -> Path:
        """A ``<path>`` with *transform* baked into its coordinates."""
        return self._with_data(self.outline().transformed(transform))

    def __mul__(self, transform: TransformLike) -> Path:
        if not isinstance(transform, _TRANSFORMS):
            return NotImplemented
        return self.transformed(transform)

    def __matmul__(self, transform: TransformLike) -> Path:
        return self.__mul__(transform)

    def __rmatmul__(self, transform: TransformLike) -> Path:
        return self.__mul__(transform)

    def _boolean(self, first: Operand, second: Operand, op: BooleanOp) -> Path:
        from ..ops.boolean import combine

        return self._result(combine(first, second, op))  # type: ignore[arg-type]

    def union(self, *others: Operand) -> Path:
        """Area covered by this outline or any of *others*."""
        from ..ops.boolean import union

        return self._result(union(self, *others))  # type: ignore[arg-type]

    def intersection(self, other: Operand) -> Path:
        from ..ops.boolean import BooleanOp

        return self._boolean(self, other, BooleanOp.INTERSECTION)

    def difference(self, other: Operand) -> Path:
        from ..ops.boolean import BooleanOp

        return self._boolean(self, other, BooleanOp.DIFFERENCE)

    def xor(self, other: Operand) -> Path:
        from ..ops.boolean import BooleanOp

        return self._boolean(self, other, BooleanOp.XOR)

    def __or__(self, other: Operand) -> Path:
        return self.union(other) if _operand(other) else NotImplemented

    def __ror__(self, other: Operand) -> Path:
        return self.union(other) if _operand(other) else NotImplemented

    def __and__(self, other: Operand) -> Path:
        return self.intersection(other) if _operand(other) else NotImplemented

    def __rand__(self, other: Operand) -> Path:
        return self.intersection(other) if _operand(other) else NotImplemented

    def __sub__(self, other: Operand) -> Path:
        return self.difference(other) if _operand(other) else NotImplemented

    def __rsub__(self, other: Operand) -> Path:
        from ..ops.boolean import BooleanOp

        return self._boolean(other, self, BooleanOp.DIFFERENCE) if _operand(other) else NotImplemented

    def __xor__(self, other: Operand) -> Path:
        return self.xor(other) if _operand(other) else NotImplemented

    def __rxor__(self, other: Operand) -> Path:
        return self.xor(other) if _operand(other) else NotImplemented

    def simplified(self) -> Path:
        """Same area without overlaps or self-intersections (skia)."""
        from ..ops.boolean import simplify

        return self._result(simplify(self))

    def stroked(
        self,
        width: float | None = None,
        *,
        cap: Cap | None = None,
        join: Join | None = None,
        miter_limit: float | None = None,
    ) -> Path:
        """The stroke as a filled ``<path>`` (skia).

        Unset arguments come from this element's ``stroke-*`` attributes.
        The result is filled with the stroke paint and has no stroke.
        """
        from ..attributes.length import Length
        from ..ops.measure import DEFAULT_MITER_LIMIT, stroke_to_path

        width = width if width is not None else Length.parse(self.get("stroke-width", 1)).to_user_units()
        data = stroke_to_path(
            self,
            width,
            cap=cap or str(self.get("stroke-linecap", "butt")),  # type: ignore[arg-type]
            join=join or str(self.get("stroke-linejoin", "miter")),  # type: ignore[arg-type]
            miter_limit=miter_limit if miter_limit is not None else float(self.get("stroke-miterlimit", DEFAULT_MITER_LIMIT)),
        )
        path = self._result(data)
        path.set("fill", self.get("stroke", "black"))
        for name in ("stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray"):
            path.discard(name)
        return path

    def exact_bbox(self) -> BBox:
        """Tight bounding box of the transformed outline (skia)."""
        from ..ops.measure import bounds

        return bounds(self)

    def contains_point(self, x: float, y: float) -> bool:
        """Whether ``(x, y)`` lies inside the filled outline (skia)."""
        from ..ops.measure import contains

        return contains(self, x, y)

    def total_length(self) -> float:
        """Length of the outline, like ``getTotalLength()`` (skia)."""
        from ..ops.measure import total_length

        return total_length(self)

    def point_at_length(self, distance: float) -> Point:
        """Point *distance* along the outline, like ``getPointAtLength()`` (skia)."""
        from ..ops.measure import point_at_length

        return point_at_length(self, distance)


def _operand(value: object) -> bool:
    return isinstance(value, (PathOperand, PathData, str))
