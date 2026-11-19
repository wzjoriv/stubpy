"""Live objects and the source merge per symbol and per parameter: each side fills what the other cannot see."""
from __future__ import annotations

import stubpy
from stubpy import Config
from tests.conftest import make_stub_ctx, write_tree

WRAPPED = """
    def logged(fn):
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper

    @logged
    def draw(x: int, y: int, *, color: str = "red") -> None: ...

    def shape(name: str, **kwargs) -> None:
        draw(**kwargs)

    class Base:
        @logged
        def __init__(self, width: int, height: int = 2) -> None: ...

    class Child(Base):
        def __init__(self, tag: str, **kwargs) -> None:
            super().__init__(**kwargs)
"""


def test_opaque_wrapper_takes_the_source_signature():
    stub, _ = make_stub_ctx(WRAPPED)
    assert "def draw(*args" not in stub
    assert "    x: int,\n    y: int,\n    *,\n    color: str = 'red',\n) -> None: ..." in stub
    assert "def __init__(self, width: int, height: int = 2) -> None: ..." in stub


def test_variadics_runtime_cannot_close_are_closed_from_source():
    stub, _ = make_stub_ctx(WRAPPED)
    shape = stub.split("def shape(")[1].split("class Base")[0]
    assert "**kwargs" not in shape and "color: str = 'red'" in shape
    child = stub.split("class Child(Base):")[1]
    assert "**kwargs" not in child and "width: int," in child and "height: int = 2," in child


def test_merged_output_matches_source_only_output():
    imported, _ = make_stub_ctx(WRAPPED)
    source_only, _ = make_stub_ctx(WRAPPED, imports="none")
    assert imported == source_only


def test_module_attribute_default_keeps_its_source_text():
    stub, _ = make_stub_ctx("""
        import math
        import os
        def f(sep: str = os.sep, angle: float = math.pi, n: int = 3) -> None: ...
    """)
    assert "sep: str = os.sep" in stub and "angle: float = math.pi" in stub and "n: int = 3" in stub
    assert "import math\nimport os" in stub


def test_class_attribute_keeps_the_alias_the_source_wrote():
    stub, _ = make_stub_ctx("""
        from typing import Union
        Length = Union[int, float, str]
        class Shape:
            width: Length
            height: int
    """)
    assert "    width: Length\n    height: int" in stub
    assert "int | float | str\n" not in stub.split("class Shape")[1]


def test_type_checking_name_from_another_module_is_imported(tmp_path):
    root = write_tree(tmp_path / "src", {
        "mergepkg/__init__.py": "",
        "mergepkg/a.py": """
            import os
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from decimal import Decimal
            class Shape:
                def __init__(self, d: "Decimal", sep: str = os.sep) -> None: ...
        """,
        "mergepkg/b.py": """
            from .a import Shape
            class Rect(Shape):
                def __init__(self, h: int, **kwargs) -> None:
                    super().__init__(**kwargs)
        """,
    })
    out = tmp_path / "out"
    report = stubpy.generate(str(root / "mergepkg"), str(out), config=Config())
    assert report.ok, report.summary()
    rect = (out / "mergepkg" / "b.pyi").read_text(encoding="utf-8")
    assert "from decimal import Decimal" in rect and "import os" in rect
    assert "d: Decimal," in rect and "sep: str = os.sep," in rect
