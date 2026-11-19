"""
Gaps a comparison with other stub generators found: attributes, class keywords, source-over-runtime types.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

import stubpy
from stubpy import Config
from stubpy.analysis.syntax import required_python
from stubpy.compiled.pyx import infer_returns, read_pyx
from tests.conftest import write_tree

PACKAGE = {
    "gpkg/__init__.py": "",
    "gpkg/desc.py": textwrap.dedent('''\
        from typing import Generic, TypeVar, overload

        T = TypeVar("T")


        class Field(Generic[T]):
            def __init__(self, convert=None) -> None:
                self.convert = convert

            @overload
            def __get__(self, obj: None, owner: type | None = None) -> "Field[T]": ...
            @overload
            def __get__(self, obj: object, owner: type | None = None) -> T | None: ...
            def __get__(self, obj, owner=None):
                return self
    '''),
    "gpkg/shapes.py": textwrap.dedent('''\
        from typing import Any
        from .desc import Field

        Value = Any
        Child = int | str


        class Length:
            pass


        class Base:
            def __init_subclass__(cls, tag: str = "", **kwargs: Any) -> None:
                super().__init_subclass__(**kwargs)
                cls.tag = tag

            def __init__(self, *items: Child, **attrs: Value) -> None:
                self.parent = None
                self.items = list(items)


        class Circle(Base, tag="circle"):
            cx = Field[Length](convert=float)

            def __init__(self, cx: float = 0, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.cx = cx
                self.parent = compute()
                self.scale = compute()

            @property
            def area(self) -> float:
                return 0.0


        def set_value(name: str, value: Value) -> None: ...


        def compute():
            return 1
    '''),
}


@pytest.fixture(params=["all", "none"])
def shapes(request, tmp_path) -> str:
    root = write_tree(tmp_path, PACKAGE)
    result = stubpy.render(root / "gpkg" / "shapes.py", config=Config(imports=request.param))
    assert result.ok, result.diagnostics
    return result.text


def _section(text: str, start: str) -> str:
    body = text.split(start, 1)[1]
    return start + body.split("\nclass ", 1)[0].split("\ndef ", 1)[0]


def test_generic_descriptor_from_another_module_is_typed(shapes):
    fields = _section(shapes, "class Circle(").split("def ", 1)[0]
    assert "    cx: Length | None\n" in fields
    assert fields.count("cx:") == 1


def test_untyped_instance_attribute_falls_back_to_any_unless_inherited(shapes):
    circle = _section(shapes, "class Circle(")
    assert "    scale: Any\n" in circle
    assert "parent" not in circle and "area:" not in circle
    assert "    parent: Any\n" in _section(shapes, "class Base:")


def test_class_keywords_are_kept(shapes):
    assert "class Circle(Base, tag='circle'):" in shapes or 'class Circle(Base, tag="circle"):' in shapes


def test_alias_of_a_typing_form_is_kept(shapes):
    assert "def set_value(name: str, value: Value) -> None: ..." in shapes


def test_forwarded_star_args_take_the_target_type(shapes):
    init = _section(shapes, "class Circle(").split("def __init__", 1)[1]
    assert "*args: Child," in init


def test_any_count_matches_between_import_modes(tmp_path):
    root = write_tree(tmp_path, PACKAGE)
    counts = [stubpy.render(root / "gpkg" / "shapes.py", config=Config(imports=mode)).text.count("Any")
              for mode in ("all", "none")]
    assert counts[0] <= counts[1]


@pytest.mark.parametrize(("source", "needs"), [
    ("type X = int\n", (3, 12)),
    ("def f[T](x: T) -> T: ...\n", (3, 12)),
    ("class C[T]: ...\n", (3, 12)),
    ("try:\n    pass\nexcept* ValueError:\n    pass\n", (3, 11)),
    ("try:\n    pass\nexcept A, B:\n    pass\n", (3, 14)),
])
def test_required_python(source, needs):
    found = required_python(source, running=(3, 10))
    assert found is not None and found[0] == needs


def test_required_python_ignores_what_the_interpreter_has():
    assert required_python("type X = int\n", running=(3, 12)) is None
    assert required_python("def f(:\n", running=(3, 10)) is None


@pytest.mark.skipif(sys.version_info >= (3, 12), reason="checks a source this Python cannot parse")
def test_newer_syntax_is_skipped_with_a_warning_and_does_not_fail_the_run(tmp_path):
    root = write_tree(tmp_path, {"pkg/__init__.py": "", "pkg/new.py": "type X = int\n", "pkg/old.py": "x: int = 1\n"})
    report = stubpy.generate(root / "pkg", tmp_path / "out")
    assert report.ok and not report.failed
    assert not (tmp_path / "out" / "pkg" / "new.pyi").exists()
    assert (tmp_path / "out" / "pkg" / "old.pyi").exists()


def test_genuine_syntax_error_still_fails(tmp_path):
    src = write_tree(tmp_path, {"bad.py": "def f(:\n"}) / "bad.py"
    result = stubpy.render(src)
    assert not result.ok and "does not parse" in result.errors[0].message


PYX = textwrap.dedent('''\
    import numpy as np

    cdef class Tile:
        cdef public double scale
        cdef float[:, ::1] _data

        @property
        def width(self):
            return self._data.shape[1]

        @property
        def factor(self):
            return self.scale

        def pixels(self):
            out = np.zeros((2, 2), dtype=np.uint8)
            return out

        def copy(self):
            return Tile()

        cpdef fill(self, double value):
            self.scale = value

        def items(self):
            yield 1

    def count(int n, bint flag=False):
        cdef Py_ssize_t total = n
        if flag:
            return None
        return total

    def unknown(x):
        return x.thing()

    def maybe(int n):
        return n if n else "none"
''')


def _returns(name: str) -> str | None:
    return infer_returns(read_pyx(PYX), PYX).signatures()[name].returns


@pytest.mark.parametrize(("name", "expected"), [
    ("Tile.width", "int"),
    ("Tile.factor", "float"),
    ("Tile.pixels", "numpy.typing.NDArray[numpy.uint8]"),
    ("Tile.copy", "Tile"),
    ("Tile.fill", "None"),
    ("Tile.items", None),
    ("count", "int | None"),
    ("unknown", None),
    ("maybe", "int | str"),
])
def test_pyx_return_inference(name, expected):
    assert _returns(name) == expected


def test_pyx_declared_return_is_kept():
    src = "cpdef double f(int n):\n    return n\n"
    assert infer_returns(read_pyx(src), src).functions[0].returns == "double"


def test_unbuilt_pyx_stub_gets_property_and_method_types(tmp_path):
    root = write_tree(tmp_path, {"pkg/__init__.py": "", "pkg/_fast.pyx": PYX})
    report = stubpy.generate(root / "pkg", tmp_path / "out")
    assert report.ok
    text = (tmp_path / "out" / "pkg" / "_fast.pyi").read_text(encoding="utf-8")
    assert "def width(self) -> int: ..." in text
    assert "def pixels(self) -> numpy.typing.NDArray[numpy.uint8]: ..." in text
    assert "def count(n: int, flag: bool = False) -> int | None: ..." in text
