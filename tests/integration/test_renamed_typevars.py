"""A TypeVar bound under another name outside ``TYPE_CHECKING`` keeps the name the source writes."""
from __future__ import annotations

TYPES = '''
from typing import TypeVar
T = TypeVar("T")
FrameT = TypeVar("FrameT", bound=int)
'''

SELECT = '''
from __future__ import annotations
from typing import TYPE_CHECKING, Generic
if TYPE_CHECKING:
    from rtv._types import FrameT
else:
    from rtv._types import T
    FrameT = T


class Select(Generic[FrameT]):
    def __init__(self, obj: FrameT, n: int) -> None:
        self.obj = obj

    def first(self) -> FrameT: ...
'''


def test_renamed_typevar_keeps_source_name(tmp_path):
    from stubpy import generate

    pkg = tmp_path / "rtv"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "_types.py").write_text(TYPES)
    (pkg / "select.py").write_text(SELECT)
    generate(pkg, tmp_path / "out")
    stub = (tmp_path / "out" / "rtv" / "select.pyi").read_text()
    assert "class Select(Generic[FrameT]):" in stub
    assert "def __init__(self, obj: FrameT, n: int) -> None" in stub
    assert "def first(self) -> FrameT" in stub
    assert "[T]" not in stub and ": T" not in stub
