"""Stub quality: alias names, header imports, re-exports, statically known branches and hidden symbols."""
from __future__ import annotations

import ast
import re

import stubpy
from stubpy.config import Config
from tests.conftest import make_stub_ctx, write_tree


def _generate(tmp_path, files: dict[str, str]):
    """Write a package tree, generate its stubs and return ``(report, stub root)``."""
    root = write_tree(tmp_path / "src", files)
    out = tmp_path / "out"
    report = stubpy.generate(str(root), str(out), config=Config())
    assert not report.failed, [r.diagnostics for r in report.failed]
    return report, out


def test_same_module_union_alias_keeps_its_name():
    stub, _ = make_stub_ctx("""
        from __future__ import annotations
        from typing import TypeAlias
        Length: TypeAlias = str | float | int
        def scale(x: Length, factor: Length | None = None) -> Length: ...
    """)
    assert "def scale(x: Length, factor: Length | None = None) -> Length: ..." in stub


def test_same_module_alias_kept_without_future_import():
    stub, _ = make_stub_ctx("""
        from typing import Union
        Length = Union[str, float, int]
        def scale(x: Length) -> Length: ...
    """)
    assert "def scale(x: Length) -> Length: ..." in stub


def test_imported_alias_and_forwarded_alias_carry_their_import(tmp_path):
    _, out = _generate(tmp_path, {
        "aliaspkg/__init__.py": "",
        "aliaspkg/units.py": """
            from typing import Union
            class Length: ...
            LengthLike = Union[Length, float, int, str]
        """,
        "aliaspkg/base.py": """
            from __future__ import annotations
            from .units import LengthLike
            class Shape:
                def __init__(self, *, stroke_width: LengthLike | None = None) -> None: ...
        """,
        "aliaspkg/shapes/__init__.py": "",
        "aliaspkg/shapes/rect.py": """
            from __future__ import annotations
            from typing import Any
            from ..base import Shape
            class Rect(Shape):
                def __init__(self, width: float = 0, **kwargs: Any) -> None:
                    super().__init__(**kwargs)
        """,
    })
    base = (out / "aliaspkg" / "base.pyi").read_text(encoding="utf-8")
    assert "stroke_width: LengthLike | None = None" in base
    assert "from .units import LengthLike" in base
    rect = (out / "aliaspkg" / "shapes" / "rect.pyi").read_text(encoding="utf-8")
    assert "stroke_width: LengthLike | None = None" in rect
    assert "from ..units import LengthLike" in rect
    assert "Length | float | int | str" not in rect


def test_source_import_wins_over_a_typing_name_and_lines_are_merged(tmp_path):
    _, out = _generate(tmp_path, {
        "hdrpkg/__init__.py": "",
        "hdrpkg/container.py": "class Container: ...\n",
        "hdrpkg/tp.py": """
            import sys
            if sys.version_info >= (3, 11):
                from typing import Self
            else:
                from typing_extensions import Self
        """,
        "hdrpkg/user.py": """
            from __future__ import annotations
            from abc import ABC, abstractmethod
            from typing import Iterable
            from .container import Container
            from .tp import Self
            class Box(Container, ABC):
                @abstractmethod
                def items(self) -> Iterable[Container]: ...
                def copy(self) -> Self: ...
        """,
    })
    text = (out / "hdrpkg" / "user.pyi").read_text(encoding="utf-8")
    imports = [n for n in ast.parse(text).body if isinstance(n, (ast.Import, ast.ImportFrom))]
    bound = [a.asname or a.name for n in imports for a in n.names]
    assert len(bound) == len(set(bound)), text
    assert "from .container import Container" in text
    assert "from typing_extensions import Self" in text, "tp only imports Self, so its stub does not export it"
    assert "from abc import ABC, abstractmethod" in text
    assert not re.search(r"^from typing import .*\bContainer\b", text, re.M)


_TYPE_CHECKING_SOURCE = """
    import sys
    from typing import TYPE_CHECKING, TypeVar
    if TYPE_CHECKING or sys.version_info >= (3, 11):
        from typing import Self
    else:
        Self = TypeVar("Self")
    if sys.version_info >= (3, 0):
        def g(a: int) -> int: ...
    else:
        def g(a: int, b: int) -> int: ...
    __all__ = ["Self", "g"]
"""


def test_type_checking_branch_wins_over_runtime_fallback():
    stub, _ = make_stub_ctx(_TYPE_CHECKING_SOURCE)
    assert "Self = TypeVar" not in stub
    assert "Self as Self" in stub
    assert stub.endswith(
        "if sys.version_info >= (3, 0):\n"
        "    def g(a: int) -> int: ...\n"
        "else:\n"
        "    def g(a: int, b: int) -> int: ...\n"
    )


def test_resolved_version_branch_keeps_taken_definition():
    stub, _ = make_stub_ctx(_TYPE_CHECKING_SOURCE, version_branches="resolve")
    assert "Self = TypeVar" not in stub and "Self as Self" in stub
    assert "def g(a: int) -> int: ..." in stub and "b: int" not in stub and "if sys" not in stub


def test_symbols_outside_all_are_emitted_when_referenced():
    stub, _ = make_stub_ctx("""
        from typing import Generic, TypeVar
        T = TypeVar("T")
        class _Base:
            def size(self) -> int: ...
        class Box(_Base, Generic[T]):
            def get(self) -> T: ...
        class _Unused: ...
        __all__ = ["Box"]
    """)
    assert "T = TypeVar('T')" in stub
    assert "class _Base:" in stub
    assert "_Unused" not in stub
    assert '__all__ = ["Box"]' in stub


def test_optional_import_fallback_does_not_leak():
    stub, _ = make_stub_ctx("""
        try:
            from stubpy import hint
        except ImportError:
            class hint:
                @staticmethod
                def signature(text):
                    return lambda f: f
        try:
            from _stubpy_missing_fast import f
        except ImportError:
            def f(x: int) -> int: ...
        @hint.signature("(x: float) -> float")
        def g(x): ...
    """)
    assert "class hint" not in stub
    assert "def f(x: int) -> int: ..." in stub
    assert "def g(x: float) -> float: ..." in stub


def test_all_lists_only_names_the_stub_binds(tmp_path):
    _, out = _generate(tmp_path, {
        "allpkg/__init__.py": """
            def __getattr__(name):
                raise AttributeError(name)
            def f() -> None: ...
            __all__ = ["f", "lazy_only"]
        """,
    })
    text = (out / "allpkg" / "__init__.pyi").read_text(encoding="utf-8")
    assert '__all__ = ["f"]' in text
