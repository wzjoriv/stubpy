"""Getset types and overload docstrings read from binding docstrings; enum defaults from other in-scope enums."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import stubpy
from stubpy import Config
from stubpy.analysis.harvest.models import NonLiteralDefault
from stubpy.compiled.introspect._doc_types import doc_type, variant_docs
from stubpy.core.context import StubContext
from stubpy.emit.annotations.defaults import render_default

PACKAGE = Path(__file__).resolve().parents[2] / "demos" / "svgraster" / "svgraster"


@pytest.mark.parametrize(("doc", "expected"), [
    ("counts: object", "object"),
    ("width: float\n\nColumns.", "float"),
    ("(self) -> float\n\nThe width.", "float"),
    ("Columns in the coverage buffer.", None),
    (None, None),
])
def test_doc_type(doc, expected):
    name = "counts" if doc and doc.startswith("counts") else "width"
    assert doc_type(name, doc) == expected


def test_variant_docs():
    doc = "f(*args, **kwargs)\nOverloaded function.\n\n1. f(x: int) -> int\n\nFirst.\n\n2. f(x: str) -> str\n\nSecond.\n"
    assert variant_docs(doc) == ["First.", "Second."]
    assert variant_docs("plain") == []


def test_enum_default_from_an_imported_enum():
    ctx = StubContext()
    ctx.extra_imports["Mode"] = "from ._other import Mode"
    assert render_default(NonLiteralDefault("Mode.FAST"), ctx) == "Mode.FAST"
    assert render_default(NonLiteralDefault("Kind.FAST"), StubContext()) == "..."


def _importable() -> bool:
    sys.path.insert(0, str(PACKAGE.parent))
    try:
        import svgraster._codec  # noqa: F401
        return True
    except Exception:
        return False
    finally:
        sys.path.remove(str(PACKAGE.parent))


@pytest.mark.skipif(not _importable(), reason="svgraster's extensions are not built for this interpreter")
def test_svgraster_getset_types_and_overload_docs(tmp_path):
    report = stubpy.generate(PACKAGE, tmp_path, config=Config(include_docstrings=True))
    assert report.ok, report.summary()
    codec = (tmp_path / "svgraster" / "_codec.pyi").read_text(encoding="utf-8")
    assert "def counts(self) -> object:" in codec
    filters = (tmp_path / "svgraster" / "_filters.pyi").read_text(encoding="utf-8")
    assert '"""feGaussianBlur with one deviation in pixels."""' in filters
