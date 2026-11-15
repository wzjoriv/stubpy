"""Stubs for ``demos/svgraster``: real C API, Cython, pybind11 and nanobind modules (built for one interpreter)."""
from __future__ import annotations

import ast
import importlib
import shutil
import sys
from pathlib import Path

import pytest

import stubpy
from stubpy.cli import main

DEMO = Path(__file__).resolve().parents[2] / "demos" / "svgraster"
PACKAGE = DEMO / "svgraster"


def _importable() -> bool:
    """True when ``svgraster._filters`` imports from the demo folder on this interpreter."""
    if not PACKAGE.is_dir():
        return False
    sys.path.insert(0, str(DEMO))
    try:
        importlib.import_module("svgraster._filters")
        return True
    except Exception:
        return False
    finally:
        sys.path.remove(str(DEMO))


pytestmark = pytest.mark.skipif(not _importable(), reason="svgraster's extensions are not built for this interpreter")


@pytest.fixture(scope="module")
def stubs(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("svgraster-stubs")
    report = stubpy.generate(PACKAGE, out)
    assert report.ok, report.summary()
    return out / "svgraster"


def _read(stubs: Path, rel: str) -> str:
    return (stubs / rel).read_text(encoding="utf-8")


def _block(text: str, header: str) -> str:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i][0].isspace()
                and not lines[i].startswith(")")), len(lines))
    return "\n".join(lines[start:end])


def test_every_extension_is_stubbed_and_every_stub_parses(stubs):
    for name in ("_scanline", "_paint", "_pattern", "_filters", "_composite"):
        assert (stubs / f"{name}.pyi").is_file(), name
    for stub in stubs.rglob("*.pyi"):
        ast.parse(stub.read_text(encoding="utf-8"), filename=str(stub))


def test_check_matches_generate(stubs):
    assert stubpy.check(PACKAGE, stubs.parent).ok


def test_pybind11_overloads(stubs):
    text = _read(stubs, "_filters.pyi")
    for name in ("gaussian_blur", "flood"):
        assert text.count(f"def {name}(") == 2
        assert f"@overload\ndef {name}(" in text


def test_pybind11_enum(stubs):
    blend = _block(_read(stubs, "_filters.pyi"), "class BlendMode")
    assert "NORMAL: ClassVar[BlendMode]" in blend and "LUMINOSITY: ClassVar[BlendMode]" in blend
    assert "def value(self) -> int: ..." in blend


def test_nanobind_enum(stubs):
    text = _read(stubs, "_composite.pyi")
    assert "class LineJoin(Enum):\n    MITER = 0" in text


def test_read_only_and_writable_properties(stubs):
    light = _block(_read(stubs, "_filters.pyi"), "class LightSource")
    assert "def kind(self) -> LightType: ..." in light and "@kind.setter" not in light
    assert "@position.setter" in light
    rasterizer = _block(_read(stubs, "_scanline.pyi"), "class Rasterizer")
    assert "@width.setter" not in rasterizer and "@height.setter" not in rasterizer
    assert "@samples.setter" in rasterizer


def test_constructor_overloads(stubs):
    transfer = _block(_read(stubs, "_filters.pyi"), "class TransferFunction")
    assert transfer.count("def __init__(") == 4


def test_text_signatures_keep_positional_only(stubs):
    text = _read(stubs, "_scanline.pyi")
    assert "def polygon_area(points, /): ..." in text
    assert "    /,\n)" in _block(text, "def fill_polygons(")


def test_cython_c_types(stubs):
    text = _read(stubs, "_paint.pyi")
    lut = _block(text, "class GradientLUT")
    assert "offsets: Buffer" in lut and "size: int = 1024" in lut and "linear_rgb: bool = False" in lut
    assert "def sample(self, t: float, spread: int = ...) -> tuple: ..." in lut
    assert "x1: float" in _block(text, "def linear_gradient(") and ") -> None: ..." in _block(text, "def linear_gradient(")


def test_nanobind_keyword_only(stubs):
    over = _block(_read(stubs, "_composite.pyi"), "def over(")
    assert "*,\n    opacity: float = 1.0," in over
    assert "dst: numpy.typing.NDArray[numpy.float32]" in over


def test_subclass_inherits_compiled_constructor(stubs):
    text = _read(stubs, "raster/rasterizer.pyi")
    rasterizer = _block(text, "class Rasterizer(")
    assert rasterizer.startswith("class Rasterizer(_scanline.Rasterizer):")
    assert "width: int" in rasterizer and "rule: str = 'nonzero'" in rasterizer and "samples: int = 4" in rasterizer
    assert "**kwargs" not in rasterizer
    lut = _block(_read(stubs, "raster/paint.pyi"), "class GradientLUT(")
    assert "size: int = 1024" in lut and "linear_rgb: bool = False" in lut


def test_function_kwargs_resolved(stubs):
    blur = _block(_read(stubs, "filters/__init__.pyi"), "def blur(")
    assert "sy: float | None = None" in blur and "**kwargs" not in blur


def test_numba_functions_are_plain_defs(stubs):
    text = _read(stubs, "_jit.pyi")
    assert "def downscale(" in text and "use_jit: bool = True" in text and "Dispatcher" not in text


def test_docsync_round_trip(stubs, tmp_path, capsys):
    stub = tmp_path / "_filters.pyi"
    shutil.copy(stubs / "_filters.pyi", stub)
    original = stub.read_text(encoding="utf-8")
    sys.path.insert(0, str(DEMO))
    try:
        assert main(["docstrings", "check", str(stub), "-m", "svgraster._filters"]) == 1
        result = stubpy.sync_docstrings(stub, "svgraster._filters")
        assert "gaussian_kernel" in result.updated and "LightSource" in result.updated
        assert not stubpy.sync_docstrings(stub, "svgraster._filters").changed
        assert main(["docstrings", "check", str(stub), "-m", "svgraster._filters"]) == 0
    finally:
        sys.path.remove(str(DEMO))
    synced = stub.read_text(encoding="utf-8")
    assert '"""Normalized 1-D Gaussian weights."""' in synced
    assert _without_docstrings(synced) == _without_docstrings(original)


def _without_docstrings(text: str) -> str:
    """The AST dump of *text* with every docstring replaced by ``...``."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Expr(ast.Constant(...))]
    return ast.dump(tree)


def test_cli_module_option_and_dotted_target(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(DEMO)
    assert main(["generate", "-m", "svgraster._composite", "-o", str(tmp_path / "a")]) == 0
    assert "def over(" in (tmp_path / "a" / "svgraster" / "_composite.pyi").read_text(encoding="utf-8")
    assert main(["generate", "svgraster._scanline", "-o", str(tmp_path / "b")]) == 0
    assert (tmp_path / "b" / "svgraster" / "_scanline.pyi").is_file()
    capsys.readouterr()
    assert main(["render", "svgraster._filters"]) == 0
    assert "class LightSource:" in capsys.readouterr().out


def test_render_extension_file_path():
    path = next(PACKAGE.glob("_paint.*.pyd"), None) or next(PACKAGE.glob("_paint.*.so"))
    result = stubpy.render(path)
    assert result.ok and result.module_name == "svgraster._paint"
    assert "class GradientLUT:" in result.text


def test_subclass_forwarding_unchanged_copies_pybind11_overloads(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(DEMO))
    src = tmp_path / "transfer_sub.py"
    src.write_text(
        "from svgraster._filters import TransferFunction, TransferType\n\n"
        "class Transfer(TransferFunction):\n"
        "    def __init__(self, *args, **kwargs):\n"
        "        super().__init__(*args, **kwargs)\n",
        encoding="utf-8",
    )
    text = stubpy.render(src).text
    ast.parse(text)
    block = _block(text, "class Transfer(")
    assert block.count("@overload") == 4
    assert "def __init__(self) -> None: ..." in block
    assert "kind: TransferType," in block
    assert "values: Sequence[SupportsFloat | SupportsIndex]" in block
    assert "intercept: SupportsFloat | SupportsIndex = 0.0" in block
    assert "*args" not in block
