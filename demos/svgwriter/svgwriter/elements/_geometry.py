"""``PathOperand``: outlines, path conversion and geometric operators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Final, TypeAlias, Union

from ..path.data import PathData
from ..transform import Matrix, TransformLike, TransformOp, Transform, as_transform
from .base import Element

if TYPE_CHECKING:
    from .shapes import Path

__all__ = ["Operand", "PathOperand"]

Operand: TypeAlias = Union["PathOperand", PathData, str]

NOT_COPIED: Final = frozenset({"id", "transform"})
_TRANSFORMS: Final = (Transform, TransformOp, Matrix, str)


class PathOperand(Element):
    """An element with an outline.

    Adds :meth:`to_path`, transforms baked with ``*``/``@`` and, with
    skia-python installed, boolean operators:

    ========  ==============================
    ``a | b`` union
    ``a & b`` intersection
    ``a - b`` difference
    ``a ^ b`` exclusive or
    ``a * t`` bake transform *t* (also ``a @ t``)
    ========  ==============================
    """

    geometry_attributes: ClassVar[frozenset[str]] = frozenset()

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

    def _result(self, data: PathData) -> Path:
        path = self.to_path()
        path.d = data
        path.discard("fill-rule")
        return path

    def transformed(self, transform: TransformLike) -> Path:
        """A ``<path>`` with *transform* baked into its coordinates."""
        path = self.to_path()
        path.d = self.outline().transformed(transform)
        return path

    def __mul__(self, transform: TransformLike) -> Path:
        if not isinstance(transform, _TRANSFORMS):
            return NotImplemented
        return self.transformed(transform)

    def __matmul__(self, transform: TransformLike) -> Path:
        return self.__mul__(transform)

    def __rmatmul__(self, transform: TransformLike) -> Path:
        return self.__mul__(transform)

    def _boolean(self, first: Operand, second: Operand, op: str) -> Path:
        from ..ops import combine

        return self._result(combine(first, second, op))

    def __or__(self, other: Operand) -> Path:
        return self._boolean(self, other, "union") if _operand(other) else NotImplemented

    def __ror__(self, other: Operand) -> Path:
        return self._boolean(self, other, "union") if _operand(other) else NotImplemented

    def __and__(self, other: Operand) -> Path:
        return self._boolean(self, other, "intersection") if _operand(other) else NotImplemented

    def __rand__(self, other: Operand) -> Path:
        return self._boolean(self, other, "intersection") if _operand(other) else NotImplemented

    def __sub__(self, other: Operand) -> Path:
        return self._boolean(self, other, "difference") if _operand(other) else NotImplemented

    def __rsub__(self, other: Operand) -> Path:
        return self._boolean(other, self, "difference") if _operand(other) else NotImplemented

    def __xor__(self, other: Operand) -> Path:
        return self._boolean(self, other, "xor") if _operand(other) else NotImplemented

    def __rxor__(self, other: Operand) -> Path:
        return self._boolean(self, other, "xor") if _operand(other) else NotImplemented


def _operand(value: object) -> bool:
    return isinstance(value, (PathOperand, PathData, str))
