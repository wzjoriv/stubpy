"""``<path>`` and its composition operators."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, ClassVar, overload

from ..._internal._typing import Self
from ...attributes.descriptors import Attr
from ...path.builder import PathBuilder
from ...path.data import BBox, PathData, PathDataLike
from ...transform.transform import TransformLike
from .._geometry import Operand
from ..base import Element
from ._base import Shape

if TYPE_CHECKING:
    from ..structure import Group

__all__ = ["Path"]


class Path(Shape, tag="path"):
    """``<path>``.

    Parameters
    ----------
    d : str, PathData, PathBuilder or iterable of commands
        The path data.
    path_length : float, optional
        Author's computed total length.
    **kwargs
        Presentation, core, conditional and other attributes.

    Notes
    -----
    ``p1 + p2`` appends ``p2``'s subpaths to a copy of ``p1``; ``p += p2``
    does it in place. ``p * t`` and ``p @ t`` bake a transform; ``*=`` and
    ``@=`` do it in place, as do ``|=``, ``&=``, ``-=`` and ``^=`` for the
    boolean operations.

    Examples
    --------
    >>> a = Path("M0 0 H10", stroke="red")
    >>> str(a + Path("M0 5 H10"))
    '<path stroke="red" d="M0 0 H10 M0 5 H10"/>'
    """

    geometry_attributes: ClassVar[frozenset[str]] = frozenset({"d", "pathLength"})
    path_length = Attr[float](convert=float)

    def __init__(self, d: PathDataLike | PathBuilder = "", *, path_length: float | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.d = d  # type: ignore[assignment]
        self.update(path_length=path_length)

    @property
    def d(self) -> PathData:
        raw = self.attributes.get("d", "")
        return raw if isinstance(raw, PathData) else PathData(raw)

    @d.setter
    def d(self, value: PathDataLike | PathBuilder) -> None:
        if isinstance(value, PathBuilder):
            value = value.build()
        self.attributes["d"] = value if isinstance(value, PathData) else PathData(value)

    @classmethod
    def build(cls, builder: PathBuilder, **kwargs: Any) -> Self:
        return cls(builder.build(), **kwargs)

    @classmethod
    def from_points(cls, points: Iterable[tuple[float, float]], *, closed: bool = False, **kwargs: Any) -> Self:
        builder = PathBuilder()
        for i, (x, y) in enumerate(points):
            if i == 0:
                builder.move_to(x, y)
            else:
                builder.line_to(x, y)
        if closed:
            builder.close()
        return cls(builder, **kwargs)

    @property
    def bbox(self) -> BBox:
        return self.d.bbox or BBox(0.0, 0.0, 0.0, 0.0)

    def local_outline(self) -> PathData:
        return self.d

    def _replace(self, data: PathData) -> Self:
        self.d = data
        self.discard("transform")
        return self

    @overload
    def __add__(self, other: Path | PathData | str) -> Path: ...
    @overload
    def __add__(self, other: Element | Iterable[Element]) -> Group: ...
    def __add__(self, other: Path | PathData | str | Element | Iterable[Element]) -> Path | Group:
        if isinstance(other, (Path, PathData, str)):
            clone = self.copy()
            clone.d = self.d + (other.d if isinstance(other, Path) else other)
            return clone
        return super().__add__(other)

    def __iadd__(self, other: Path | PathData | str) -> Self:
        if not isinstance(other, (Path, PathData, str)):
            return NotImplemented
        self.d = self.d + (other.d if isinstance(other, Path) else other)
        return self

    def __imul__(self, transform: TransformLike) -> Self:
        result = self.__mul__(transform)
        return NotImplemented if result is NotImplemented else self._replace(result.d)

    def __imatmul__(self, transform: TransformLike) -> Self:
        return self.__imul__(transform)

    def __ior__(self, other: Operand) -> Self:
        result = self.__or__(other)
        return NotImplemented if result is NotImplemented else self._replace(result.d)

    def __iand__(self, other: Operand) -> Self:
        result = self.__and__(other)
        return NotImplemented if result is NotImplemented else self._replace(result.d)

    def __isub__(self, other: Operand) -> Self:
        result = self.__sub__(other)
        return NotImplemented if result is NotImplemented else self._replace(result.d)

    def __ixor__(self, other: Operand) -> Self:
        result = self.__xor__(other)
        return NotImplemented if result is NotImplemented else self._replace(result.d)
