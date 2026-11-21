"""The drawlib corpus (``corpora/drawlib``): every module stubs cleanly, with and without importing it."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

import stubpy
from stubpy import Config, Level

CORPUS = Path(__file__).resolve().parents[2] / "corpora" / "drawlib" / "drawlib"
PEP695_MODULE = "_aliases312"

pytestmark = pytest.mark.skipif(not CORPUS.is_dir(), reason="drawlib corpus not present")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """Generate the corpus once; return ``(report, stub root)``."""
    out = tmp_path_factory.mktemp("drawlib")
    report = stubpy.generate(str(CORPUS), str(out), config=Config())
    return report, out / "drawlib"


@pytest.fixture(scope="module")
def source_only(tmp_path_factory):
    """Generate the corpus without importing it; return ``(report, stub root)``."""
    out = tmp_path_factory.mktemp("drawlib_no_import")
    report = stubpy.generate(str(CORPUS), str(out), config=Config(imports="none"))
    return report, out / "drawlib"


def _stub(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _section(text: str, start: str) -> str:
    """Return the block of *text* from the line starting with *start* to the next top-level statement."""
    body = text.split(start, 1)[1]
    return start + re.split(r"\n(?=\S)", body, maxsplit=1)[0]


def _assert_clean(report) -> None:
    failed = {Path(r.source).stem for r in report.failed}
    assert failed == set()
    for result in report.results:
        errors = [d for d in result.diagnostics if d.level is Level.ERROR]
        assert not errors, (result.source, errors)
        if Path(result.source).stem == PEP695_MODULE and sys.version_info < (3, 12):
            assert not result.text and any("needs Python 3.12" in d.message for d in result.warnings)


def _assert_parses(root: Path) -> None:
    stubs = list(root.rglob("*.pyi"))
    assert len(stubs) >= 35
    for path in stubs:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_failures_and_no_error_diagnostics(corpus):
    _assert_clean(corpus[0])


def test_every_stub_parses(corpus):
    _assert_parses(corpus[1])


def test_source_only_is_clean_and_parses(source_only):
    report, root = source_only
    _assert_clean(report)
    _assert_parses(root)
    assert "size: LengthLike," in _section(_stub(root, "elements/shapes/_basic.pyi"), "class Rect(")


def test_no_name_is_bound_twice(corpus):
    _, root = corpus
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
    _, root = corpus
    for path in root.rglob("*.pyi"):
        modules = [(n.level, n.module) for n in ast.parse(path.read_text(encoding="utf-8")).body
                   if isinstance(n, ast.ImportFrom) and n.names[0].name != "*"]
        assert len(modules) == len(set(modules)), path


def test_aliases_are_kept_with_their_import(corpus):
    _, root = corpus
    shapes = _stub(root, "elements/shapes/_basic.pyi")
    assert re.search(r"^from \.\.\.attributes\.length import (.*, )?LengthLike\b", shapes, re.M)
    assert "x: LengthLike = 0," in _section(shapes, "class Rect(")
    assert "Length | float | int | str" not in shapes


def test_rect_kwargs_chain(corpus):
    _, root = corpus
    rect = _section(_stub(root, "elements/shapes/_basic.pyi"), "class Rect(")
    init = rect.split("def square")[0]
    assert "stroke_width: LengthLike | None = None," in init
    assert "fill: PaintValue = None," in init
    assert "from ...color import PaintValue" in _stub(root, "elements/shapes/_basic.pyi")


def test_rect_square_resolves_through_cls_call(corpus):
    _, root = corpus
    square = _section(_stub(root, "elements/shapes/_basic.pyi"), "class Rect(").split("def square(")[1].split("def ")[0]
    assert "size: LengthLike," in square
    assert "fill: PaintValue = None," in square and "rx: LengthLike | None = None," in square


def test_package_init_reexports_star_imported_names(corpus):
    _, root = corpus
    init = _stub(root, "__init__.pyi")
    tree = ast.parse(init)
    assert not any(isinstance(n, ast.ImportFrom) and n.names[0].name == "*" for n in tree.body)
    for name in ("Rect", "FeGaussianBlur", "LinearGradient", "Animate"):
        assert f"{name} as {name}," in init
    exported = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "__all__")
    names = ast.literal_eval(exported.value)
    assert {"Rect", "FeGaussianBlur", "write_async", "Document"} <= set(names)


def test_names_hidden_by_all_are_emitted_when_referenced(corpus):
    _, root = corpus
    base = _stub(root, "elements/base.pyi")
    assert "E = TypeVar('E', bound='Element')" in base
    assert "def copy(self: E) -> E: ..." in base
    assert "class _XYCommand(PathCommand):" in _stub(root, "path/commands.pyi")


def test_stub_meaningful_decorators_are_kept(corpus):
    _, root = corpus
    document = _stub(root, "document.pyi")
    assert re.search(r"@classmethod\n    @contextmanager\n    def writing\(", document)
    assert "@contextmanager\n    def nest(" in document
    assert "@singledispatch\ndef format_value(" in _stub(root, "attributes/values.pyi")
    assert "@cached_property\n    def hsl(self)" in _stub(root, "color.pyi")


def test_descriptor_protocol_and_init_subclass(corpus):
    _, root = corpus
    attr = _stub(root, "attributes/descriptors.pyi")
    for method in ("__set_name__", "__set__", "__delete__"):
        assert f"def {method}(self" in attr
    assert attr.count("def __get__(") == 2
    assert "def __init_subclass__(\n        cls,\n        *,\n        tag: str | None = None," in _stub(
        root, "elements/base.pyi")


def test_async_generator_is_a_plain_def(corpus):
    _, root = corpus
    text = _stub(root, "io/_async.pyi")
    assert "async def write_async(" in text
    assert "async def aiter_chunks" not in text and "def aiter_chunks(" in text
    assert "-> AsyncIterator[str]: ..." in text


def test_type_checking_branch_wins(corpus):
    _, root = corpus
    typing_stub = _stub(root, "_internal/_typing.pyi")
    assert "from typing_extensions import NotRequired as NotRequired, Required as Required, Self as Self" in typing_stub
    assert "Self = TypeVar" not in typing_stub
    shapes = _stub(root, "elements/shapes/_basic.pyi")
    assert re.search(r"^from \.\.\._internal\._typing import .*\bSelf\b", shapes, re.M)
    assert not re.search(r"^from typing import .*\bSelf\b", shapes, re.M)


def test_partial_module_attributes(corpus):
    _, root = corpus
    length = _stub(root, "attributes/length.pyi")
    assert "def px(\n    value: float,\n    *,\n    unit: Unit = Unit.PX,\n) -> Length: ..." in length


def test_dataclass_initvar_and_protocol(corpus):
    _, root = corpus
    writer = _stub(root, "io/writer.pyi")
    assert "@dataclass(kw_only=True)" in writer
    assert "pretty: InitVar[bool]" in writer
    assert "pretty: InitVar[bool] = True" in writer
    assert "pretty: bool = True," in _section(writer, "class Writer:")
    assert "def __init__" not in _stub(root, "attributes/protocols.pyi")


def test_enum_aliases_and_flags(corpus):
    _, root = corpus
    categories = _stub(root, "elements/_categories.pyi")
    assert "GROUPING = CONTAINER" in categories
    assert re.search(r"class ContentModel\((enum\.)?Flag\):", categories)
    assert "USER = NONE" in _stub(root, "attributes/length.pyi")


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax needs Python 3.12+")
def test_pep695_generics(corpus):
    _, root = corpus
    text = _stub(root, f"_internal/{PEP695_MODULE}.pyi")
    assert "type Pair[T] = tuple[T, T]" in text
    assert "class Stack[T]:" in text
    assert "def first[T](items: Iterable[T], default: T) -> T: ..." in text


def _method(text: str, name: str) -> str:
    """The stub lines of method *name*, every overload included."""
    out: list[str] = []
    keep = False
    for line in text.splitlines():
        if line.startswith(f"    def {name}("):
            keep = True
        elif line.startswith(("    def ", "    @", "class ", "def ")) and not (out and out[-1] == "    @overload"):
            keep = False
        elif line and not line.startswith(" "):
            keep = False
        if keep:
            out.append(line)
    assert out, name
    return "\n".join(out)


def test_factory_shortcuts_expand_the_class_they_construct(corpus):
    _, root = corpus
    factory = _stub(root, "elements/_factory.pyi")
    assert "from .shapes import Circle, Line, Path, Rect" in factory
    circle = _method(factory, "circle")
    assert circle.rstrip().endswith("-> Circle: ...")
    assert "def circle(\n        self,\n        cx: LengthLike = 0,\n        cy: LengthLike = 0,\n        r: LengthLike = 0,\n        *,\n" in factory
    assert "*args" not in circle
    rect = _method(factory, "rect")
    assert "x: LengthLike = 0," in rect and "fill: PaintValue = None," in rect and "rx: LengthLike | None = None," in rect
    assert "*args" not in rect
    for name in ("group", "linear_gradient"):
        assert "*args: Child," in _method(factory, name)


def test_shortcuts_are_inherited_by_document_and_containers(corpus):
    _, root = corpus
    assert "class Document(ElementFactory):" in _stub(root, "document.pyi")
    assert "class GraphicsContainer(ElementFactory, " in _stub(root, "elements/container.pyi")


def test_lowercase_aliases_are_reexported(corpus):
    _, root = corpus
    aliases = _stub(root, "aliases.pyi")
    assert "circle: TypeAlias = Circle" in aliases and "linear_gradient: TypeAlias = LinearGradient" in aliases
    assert "from .elements import" in aliases
    init = _stub(root, "__init__.pyi")
    tree = ast.parse(init)
    star = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.names[0].name == "*"]
    assert not star
    imported = {a.asname for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "aliases" for a in n.names}
    assert {"circle", "rect", "linear_gradient", "fe_gaussian_blur", "svg", "path"} <= imported
    assert {"filter", "set"} <= imported
    exported = ast.literal_eval(next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "__all__").value)
    assert {"circle", "fe_gaussian_blur", "Circle"} <= set(exported)
    assert not {"filter", "set"} & set(exported)


def test_operator_dunders_and_their_overloads(corpus):
    _, root = corpus
    compose = _stub(root, "elements/_compose.pyi")
    assert "def __add__(self: Element, other: Element | Iterable[Element]) -> Group: ..." in compose
    assert "def __radd__(self: Element, other: Iterable[Element]) -> Group: ..." in compose
    path = _stub(root, "elements/shapes/_path.pyi")
    add = _section(path, "class Path(").split("    @overload\n    def __add__", 1)[1]
    assert add.startswith("(self, other: Path | PathData | str) -> Path: ...")
    assert "@overload\n    def __add__(self, other: Element | Iterable[Element]) -> Group: ..." in path
    assert path.count("def __add__(") == 2
    assert "def __iadd__(self, other: Path | PathData | str) -> Self: ..." in path
    document = _stub(root, "document.pyi")
    container = _stub(root, "elements/container.pyi")
    for line in ("def __mod__(self, element: Element) -> FuncIRI: ...",
                 "def __imod__(self, elements: Element | Iterable[Element]) -> Self: ..."):
        assert line in document and line in container
    assert "def __iadd__(self, elements: Element | Iterable[Element]) -> Self: ..." in document
    assert "def __iadd__(self, children: ChildT | Iterable[ChildT]) -> Self: ..." in container
    geometry = _stub(root, "elements/_geometry.pyi")
    for dunder in ("or", "and", "sub", "xor"):
        assert f"def __{dunder}__(self, other: Operand) -> Path: ..." in geometry
        assert f"def __r{dunder}__(self, other: Operand) -> Path: ..." in geometry
        assert f"def __i{dunder}__(self, other: Operand) -> Self: ..." in path
    assert "def __matmul__(self, transform: TransformLike) -> Path: ..." in geometry
    assert "def __rmatmul__(self, transform: TransformLike) -> Path: ..." in geometry
    assert "def __imatmul__(self, transform: TransformLike) -> Self: ..." in path
    transform = _stub(root, "transform.pyi")
    assert "@overload\n    def __matmul__(self, other: Matrix) -> Matrix: ...\n    @overload\n    def __matmul__(self, other: Point | tuple[float, float]) -> Point: ..." in transform
    assert transform.count("@overload\n    def __matmul__(") == 4
    assert "def __radd__(self, other: PathData | str | int) -> PathData: ..." in _stub(root, "path/data.pyi")


def test_optional_skia_import_leaks_no_fallback(corpus):
    _, root = corpus
    skia = _stub(root, "ops/_skia.pyi")
    assert "class MissingDependencyError(ImportError):" in skia
    assert "def available() -> bool: ..." in skia
    assert "def require_skia(feature: str) -> Any: ..." in skia
    assert "INSTALL_HINT: Final" in skia
    assert "Geometry: TypeAlias = PathOperand | PathData | str" in skia
    assert "def _load" not in skia
    for path in root.rglob("*.pyi"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import skia|from skia\b)", text, re.M), path
        assert "importlib" not in text and "= None  #" not in text, path
        assert not re.search(r"^skia\b", text, re.M), path
    ops = _stub(root, "ops/__init__.pyi")
    assert "MissingDependencyError as MissingDependencyError" in ops and "available as available" in ops


def test_typed_dict_fields_and_totality(corpus):
    _, root = corpus
    writer = _stub(root, "io/writer.pyi")
    assert "class SerializeSettings(TypedDict, total=False):" in writer
    assert "    indent: Required[str]\n    precision: int\n    xml_declaration: bool\n    encoding: NotRequired[str]" in writer


def test_subpackage_layout_is_mirrored(corpus):
    _, root = corpus
    for rel in ("elements/shapes/__init__.pyi", "elements/shapes/_basic.pyi", "elements/effects.pyi", "cli.pyi",
                "ops/__init__.pyi", "io/_async.pyi", "path/commands.pyi"):
        assert (root / rel).is_file(), rel
    shapes = _stub(root, "elements/shapes/__init__.pyi")
    assert "from ._basic import Circle as Circle, Line as Line, Rect as Rect, Shape as Shape" in shapes
    assert "def main(argv: Sequence[str] | None = None) -> int: ..." in _stub(root, "cli.pyi")


def test_registry_dispatch_overloads_per_literal_key(corpus):
    _, root = corpus
    registry = _stub(root, "elements/shapes/_registry.pyi")
    assert "REGISTRY: dict[str, type[Shape]]" in registry
    assert registry.count("@overload\ndef make_shape(") == 4
    assert "    kind: Literal['circle'],\n    *,\n    cx: LengthLike = 0," in registry
    assert "    kind: Literal['line'],\n    *,\n    x1: LengthLike = 0," in registry
    assert ") -> Rect: ..." in registry
    assert "def make_shape(kind: Literal['circle', 'rect', 'line'], **kwargs: Any) -> Shape: ..." in registry
    assert registry.count("    @overload\n    @classmethod\n    def build(") == 4
    assert "        kind: Literal['rect'],\n" in registry


def test_hash_in_a_string_default_survives_a_multiline_signature(corpus):
    _, root = corpus
    assert ("def tint(\n    element: Rect,\n    *,\n    fill: str = '#c8ccd4',\n"
                    "    stroke: str = '#2b2f36',\n    stroke_width: float = 1.0,\n) -> Rect: ...")
    assert "    fill: str = '#c8ccd4'\n" in _section(_stub(root, "theme.pyi"), "class Style:")


def test_open_keywords_are_expanded(corpus):
    _, root = corpus
    theme = _stub(root, "theme.pyi")
    save = _section(theme, "class Swatch:").split("def save(")[1].split("-> None")[0]
    assert "path: str," in save and "buffering: int = -1," in save and "closefd: bool = True," in save
    assert "**kwargs" not in save
    assert "encoding: str | None = None," in save and "opener: Callable[[str, int], int] | None = None," in save


def test_dataclass_replace_expands_into_fields(corpus):
    _, root = corpus
    variant = _method(_stub(root, "theme.pyi"), "variant")
    assert "fill: str = ..." in variant and "**changes" not in variant


def test_template_variadics_take_the_signature_of_the_method_they_forward_to(corpus):
    _, root = corpus
    render = _method(_stub(root, "theme.pyi"), "render")
    assert "name: str," in render and "scale: float = 1.0," in render
    assert "*args" not in render and "**kwargs" not in render


def test_hidden_and_non_identifier_files_are_excluded_by_default(corpus):
    report, root = corpus
    shapes = CORPUS / "elements" / "shapes"
    assert {(Path(p).name, pattern) for p, pattern in report.excluded} >= {
        (".backup_shapes.py", ".*"), ("shapes-v1.py", "<non-identifier>")}
    assert (shapes / ".backup_shapes.py").is_file() and (shapes / "shapes-v1.py").is_file()
    assert sorted(p.name for p in (root / "elements" / "shapes").iterdir()) == [
        "__init__.pyi", "_basic.pyi", "_path.pyi", "_registry.pyi"]


def test_show_excluded_lists_them(capsys, tmp_path):
    from stubpy.cli import main

    assert main([str(CORPUS), "-o", str(tmp_path / "out"), "--no-config", "--show-excluded"]) == 0
    out = capsys.readouterr().out
    assert ".backup_shapes.py (.*)" in out and "shapes-v1.py (<non-identifier>)" in out


def test_import_blocked_module_falls_back_to_source_with_an_info():
    result = stubpy.render(CORPUS / "theme.py", config=Config(imports="stdlib"))
    assert result.ok
    blocked = [d for d in result.diagnostics if "blocked by stubpy import policy" in d.message]
    assert blocked and all(d.level is Level.INFO for d in blocked)
    assert not any(d.level is Level.ERROR for d in result.diagnostics)
    assert "def tint(" in result.text and "fill: str = '#c8ccd4'," in result.text
    assert "class Style:" in result.text


def test_runtime_state_that_raises_when_inspected(corpus, source_only):
    for _, root in (corpus, source_only):
        stub = _stub(root, "runtime.pyi")
        ast.parse(stub)
        assert "settings: _LazySettings" in stub
        assert "def from_tuple(cls: type[NamedTuple], values: tuple[float, ...]) -> type[NamedTuple]: ..." in stub
        assert "    value: str" in stub and "return:" not in stub
        assert "    id: Any," in stub and "class:" not in stub
        assert "SHORT_VERSION: TypeAlias" not in stub
    assert "SHORT_VERSION: str" in _stub(corpus[1], "runtime.pyi")


def test_module_raising_base_exception_at_import():
    result = stubpy.render(CORPUS / "_gpu_backend.py")
    assert result.ok
    assert "def render(scene: object, samples: int = 4) -> bytes: ..." in result.text
    assert any("BackendUnavailable" in d.message and d.level is Level.WARNING for d in result.diagnostics)


def test_shadowed_base_from_the_parent_package_and_functional_typeddict(corpus, source_only):
    for _, root in (corpus, source_only):
        stub = _stub(root, "io/plain.pyi")
        ast.parse(stub)
        assert "class Writer(io.Writer):" in stub or "class Writer(writer.Writer):" in stub
        assert "Capabilities = TypedDict('Capabilities', {'line width': int, 'wraps': bool})" in stub


def test_type_checking_classes_reexports_and_unhashable(corpus, source_only):
    for _, root in (corpus, source_only):
        stub = _stub(root, "runtime.pyi")
        assert "class ExportOptions(TypedDict, total=False):" in stub
        assert "from typing_extensions import Buffer" in stub
        assert "__hash__: ClassVar[None]  # type: ignore[assignment]" in stub
        assert "MutableMapping as MutableMapping" in _stub(root, "compat.pyi")
