"""Cython sources (``.pyx``): read without compiling, stubbed on their own, and merged into built modules."""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

import stubpy
from stubpy.compiled.pyx import read_pyx
from stubpy.compiled.pyx._cython import available, read_with_cython

SOURCE = textwrap.dedent('''\
    """Shapes, in Cython."""
    cimport cython
    from libc.math cimport sqrt

    cdef double _hidden(double x) nogil:
        return x

    cpdef enum Fill:
        NONZERO = 0
        EVENODD

    def area(double w,
             double h=1.0,
             *,
             bint exact=False):
        """Rectangle area."""
        def helper(int z):
            return z
        return w * h

    cpdef inline double scale(double[:, ::1] buf, Fill rule=NONZERO) except -1 nogil:
        return 0.0

    def gather(*items, unsigned long n=3, **options) -> list:
        return []

    cdef class Path:
        """A path."""
        cdef public double width
        cdef readonly int count, size
        cdef object _cache

        def __init__(self, double width=1.0):
            self.width = width

        @property
        def length(self):
            """Total length."""
            return 0.0

        @staticmethod
        def unit():
            return Path()

        cpdef void close(self) except *:
            pass

        cdef void _private(self):
            pass
''')


def _sigs(module):
    out = [f.embedsignature() for f in module.functions]
    for cls in module.classes:
        out += [f"{cls.name}.{m.embedsignature()}{m.decorators}" for m in cls.methods]
    return out


def test_reader():
    module = read_pyx(SOURCE)
    assert module.doc == "Shapes, in Cython."
    assert _sigs(module) == [
        "area(double w, double h=1.0, *, bint exact=False)",
        "scale(double[:, ::1] buf, Fill rule=NONZERO) -> double",
        "gather(*items, unsigned long n=3, **options) -> list",
        "Path.__init__(self, double width=1.0)[]",
        "Path.length(self)['property']",
        "Path.unit()['staticmethod']",
        "Path.close(self) -> void[]",
    ]
    assert module.functions[0].doc == "Rectangle area."
    assert [(e.name, e.members) for e in module.enums] == [("Fill", [("NONZERO", 0), ("EVENODD", None)])]
    path = module.classes[0]
    assert path.doc == "A path." and path.attributes == {
        "width": ("double", False), "count": ("int", True), "size": ("int", True)}


@pytest.mark.skipif(not available(), reason="Cython is not installed")
def test_cython_parser_agrees_with_the_reader():
    ours, theirs = read_pyx(SOURCE), read_with_cython(SOURCE, "shapes")
    assert [s.replace("::1", ":") for s in _sigs(ours)] == _sigs(theirs)
    assert [(e.name, e.members[0]) for e in theirs.enums] == [("Fill", ("NONZERO", 0))]
    assert theirs.classes[0].attributes == ours.classes[0].attributes
    assert theirs.functions[0].doc == ours.functions[0].doc


def test_unbuilt_pyx_is_stubbed_from_source(tmp_path):
    src = tmp_path / "shapes.pyx"
    src.write_text(SOURCE, encoding="utf-8")
    result = stubpy.render(src)
    assert result.ok, result.diagnostics
    text = result.text
    ast.parse(text)
    assert "def area(\n    w: float,\n    h: float = 1.0,\n    *,\n    exact: bool = False,\n): ..." in text
    assert "rule: Fill = Fill.NONZERO" in text and ") -> float: ..." in text
    assert "class Fill(IntEnum):\n    NONZERO = 0\n    EVENODD = 1" in text
    assert "def width(self) -> float: ...\n    @width.setter" in text
    assert "def count(self) -> int: ...\n    @property" in text
    assert "_hidden" not in text and "_private" not in text and "helper" not in text and "_cache" not in text
    assert any("Cython source" in d.message for d in result.diagnostics)


def test_folder_run_stubs_an_unbuilt_pyx(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "_fast.pyx").write_text("def f(int x):\n    return x\n")
    report = stubpy.generate(tmp_path / "pkg", tmp_path / "out")
    assert report.ok
    assert (tmp_path / "out" / "pkg" / "_fast.pyi").read_text() == "def f(x: int) -> int: ...\n"


RASTER = Path(__file__).resolve().parents[2] / "corpora" / "rasterlib" / "rasterlib"


@pytest.mark.skipif(not any(RASTER.glob("_codec.*.pyd")) and not any(RASTER.glob("_codec.*.so")),
                    reason="rasterlib is not built")
def test_built_module_takes_defaults_and_field_types_from_its_pyx():
    text = stubpy.render(RASTER / "_codec.pyx").text
    table = text.split("class HuffmanTable")[1]
    assert "table_class: TableClass = TableClass.DC" in table
    assert "def table_class(self) -> TableClass: ..." in table


@pytest.mark.parametrize("name", ["_codec", "_pattern"])
def test_corpus_sources_read_and_stub(tmp_path, name):
    copy = tmp_path / f"{name}.pyx"
    copy.write_text((RASTER / f"{name}.pyx").read_text(encoding="utf-8"), encoding="utf-8")
    result = stubpy.render(copy)
    assert result.ok
    ast.parse(result.text)
    assert "Buffer" in result.text
