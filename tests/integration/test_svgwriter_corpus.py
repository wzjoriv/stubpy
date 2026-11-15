"""The svgwriter corpus (``demos/svgwriter``): every module stubs cleanly in each mode, with concrete expectations."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

import stubpy
from stubpy import Config, Level

CORPUS = Path(__file__).resolve().parents[2] / "demos" / "svgwriter" / "svgwriter"
PEP695_MODULE = "_aliases312"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="svgwriter corpus not present")


@pytest.fixture(scope="module", params=["runtime", "ast", "auto"])
def corpus(request, tmp_path_factory):
    """Generate the corpus once per mode; return ``(mode, report, stub root)``."""
    out = tmp_path_factory.mktemp(f"svgwriter_{request.param}")
    report = stubpy.generate(str(CORPUS), str(out), config=Config(mode=request.param))
    return request.param, report, out / "svgwriter"


def _stub(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _section(text: str, start: str) -> str:
    """Return the block of *text* from the line starting with *start* to the next top-level statement."""
    body = text.split(start, 1)[1]
    return start + re.split(r"\n(?=\S)", body, maxsplit=1)[0]


def test_no_failures_and_no_error_diagnostics(corpus):
    _, report, _ = corpus
    failed = {Path(r.source).stem for r in report.failed}
    expected = set() if sys.version_info >= (3, 12) else {PEP695_MODULE}
    assert failed == expected
    for result in report.results:
        errors = [d for d in result.diagnostics if d.level is Level.ERROR]
        if Path(result.source).stem == PEP695_MODULE and sys.version_info < (3, 12):
            assert errors and all("does not parse" in d.message or "SyntaxError" in d.message for d in errors)
        else:
            assert not errors, (result.source, errors)


def test_every_stub_parses(corpus):
    _, _, root = corpus
    stubs = list(root.rglob("*.pyi"))
    assert len(stubs) >= 60
    for path in stubs:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_name_is_bound_twice(corpus):
    _, _, root = corpus
    for path in root.rglob("*.pyi"):
        bound: list[str] = []
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bound += [(a.asname or a.name).split(".")[0] for a in node.names if a.name != "*"]
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in bound:
                    bound.append(node.name)
        dupes = {n for n in bound if bound.count(n) > 1}
        assert not dupes, (path, dupes)


def test_one_import_line_per_module(corpus):
    _, _, root = corpus
    for path in root.rglob("*.pyi"):
        modules = [(n.level, n.module) for n in ast.parse(path.read_text(encoding="utf-8")).body
                   if isinstance(n, ast.ImportFrom) and n.names[0].name != "*"]
        assert len(modules) == len(set(modules)), path


def test_aliases_are_kept_with_their_import(corpus):
    _, _, root = corpus
    shapes = _stub(root, "elements/shapes.pyi")
    assert "from ..attributes.length import LengthLike" in shapes
    assert "x: LengthLike = 0," in _section(shapes, "class Rect(")
    assert "Length | float | int | str" not in shapes


def test_rect_kwargs_chain(corpus):
    mode, _, root = corpus
    rect = _section(_stub(root, "elements/shapes.pyi"), "class Rect(")
    if mode == "ast":
        assert "**kwargs: Any" in rect
        return
    init = rect.split("def square")[0]
    assert "stroke_width: LengthLike | None = None," in init
    assert "fill: PaintValue = None," in init
    assert "from ..color.paint import PaintValue" in _stub(root, "elements/shapes.pyi")


def test_rect_square_resolves_through_cls_call(corpus):
    mode, _, root = corpus
    square = _section(_stub(root, "elements/shapes.pyi"), "class Rect(").split("def square(")[1].split("def ")[0]
    assert "size: LengthLike," in square
    if mode != "ast":
        assert "fill: PaintValue = None," in square and "rx: LengthLike | None = None," in square


def test_package_init_reexports_star_imported_names(corpus):
    _, _, root = corpus
    init = _stub(root, "__init__.pyi")
    tree = ast.parse(init)
    assert not any(isinstance(n, ast.ImportFrom) and n.names[0].name == "*" for n in tree.body)
    for name in ("Rect", "FeGaussianBlur", "LinearGradient", "Animate"):
        assert f"{name} as {name}," in init
    exported = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "__all__")
    names = ast.literal_eval(exported.value)
    assert {"Rect", "FeGaussianBlur", "parse", "write_async", "Document"} <= set(names)


def test_names_hidden_by_all_are_emitted_when_referenced(corpus):
    _, _, root = corpus
    base = _stub(root, "elements/base.pyi")
    assert "E = TypeVar('E', bound='Element')" in base
    assert "def copy(self: E) -> E: ..." in base
    assert "class _XYCommand(PathCommand):" in _stub(root, "path/commands.pyi")


def test_stub_meaningful_decorators_are_kept(corpus):
    _, _, root = corpus
    document = _stub(root, "document.pyi")
    assert re.search(r"@classmethod\n    @contextmanager\n    def writing\(", document)
    assert "@contextmanager\n    def group(" in document
    assert "@singledispatch\ndef format_value(" in _stub(root, "attributes/values.pyi")
    assert "@cached_property\n    def hsl(self)" in _stub(root, "color/color.pyi")


def test_descriptor_protocol_and_init_subclass(corpus):
    _, _, root = corpus
    attr = _stub(root, "attributes/descriptors.pyi")
    for method in ("__set_name__", "__set__", "__delete__"):
        assert f"def {method}(self" in attr
    assert attr.count("def __get__(") == 2
    assert "def __init_subclass__(\n        cls,\n        *,\n        tag: str | None = None," in _stub(
        root, "elements/base.pyi")


def test_async_generator_is_a_plain_def(corpus):
    _, _, root = corpus
    text = _stub(root, "io/_async.pyi")
    assert "async def write_async(" in text
    assert "async def aiter_chunks" not in text and "def aiter_chunks(" in text
    assert "-> AsyncIterator[str]: ..." in text


def test_type_checking_branch_wins(corpus):
    _, _, root = corpus
    typing_stub = _stub(root, "_internal/_typing.pyi")
    assert "Self as Self," in typing_stub
    assert "Self = TypeVar" not in typing_stub
    shapes = _stub(root, "elements/shapes.pyi")
    assert re.search(r"^from \.\._internal\._typing import .*\bSelf\b", shapes, re.M)
    assert not re.search(r"^from typing import .*\bSelf\b", shapes, re.M)


def test_partial_module_attributes(corpus):
    mode, _, root = corpus
    length = _stub(root, "attributes/length.pyi")
    if mode == "ast":
        assert "px: partial[Length]" in length and "from functools import partial" in length
    else:
        assert "def px(\n    value: float,\n    *,\n    unit: Unit = Unit.PX,\n) -> Length: ..." in length


def test_dataclass_initvar_and_protocol(corpus):
    mode, _, root = corpus
    writer = _stub(root, "io/writer.pyi")
    assert "@dataclass(kw_only=True)" in writer
    assert "pretty: InitVar[bool]" in writer
    if mode != "ast":
        assert "pretty: InitVar[bool] = True" in writer
        assert "pretty: bool = True," in _section(writer, "class Writer:")
    assert "def __init__" not in _stub(root, "attributes/protocols.pyi")


def test_enum_aliases_and_flags(corpus):
    _, _, root = corpus
    categories = _stub(root, "elements/_categories.pyi")
    assert "GROUPING = CONTAINER" in categories
    assert re.search(r"class ContentModel\((enum\.)?Flag\):", categories)
    assert "USER = NONE" in _stub(root, "attributes/length.pyi")


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax needs Python 3.12+")
def test_pep695_generics(corpus):
    _, _, root = corpus
    text = _stub(root, f"_internal/{PEP695_MODULE}.pyi")
    assert "type Pair[T] = tuple[T, T]" in text
    assert "class Stack[T]:" in text
    assert "def first[T](items: Iterable[T], default: T) -> T: ..." in text
