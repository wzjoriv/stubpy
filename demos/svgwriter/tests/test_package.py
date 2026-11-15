from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import svgwriter as svg
from svgwriter.__main__ import main
from svgwriter._internal import _speedups, _typing
from svgwriter._internal._ids import IdFactory
from svgwriter._internal._registry import Registry, chainable
from svgwriter._internal._sentinels import MISSING, MissingType

from .conftest import ROOT, wellformed


def test_metadata() -> None:
    assert svg.__author__ == "Josue N Rivera"
    assert svg.__version__.count(".") == 2


def test_all_names_resolve() -> None:
    for module_name in ("svgwriter", "svgwriter.elements", "svgwriter.io", "svgwriter.attributes", "svgwriter.path", "svgwriter.transform", "svgwriter.color", "svgwriter.builder", "svgwriter.elements.filters", "svgwriter.elements.structure"):
        module = importlib.import_module(module_name)
        for name in module.__all__:
            assert getattr(module, name) is not None, f"{module_name}.{name}"


def test_lazy_module_getattr() -> None:
    import svgwriter.io as io_pkg

    assert "parse" in dir(svg)
    assert callable(svg.parse) and callable(io_pkg.parse_file)
    with pytest.raises(AttributeError):
        _ = svg.does_not_exist  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        _ = io_pkg.nothing  # type: ignore[attr-defined]


def test_version_guarded_aliases() -> None:
    stack = _typing.Stack([1, 2])
    stack.push(3)
    assert stack.peek() == 3 and stack.pop() == 3 and len(stack) == 2 and list(stack) == [2, 1]
    expected = "svgwriter._internal._aliases312" if sys.version_info >= (3, 12) else "svgwriter._internal._stack"
    assert _typing.Stack.__module__ == expected
    if sys.version_info >= (3, 12):
        from svgwriter._internal._aliases312 import first

        assert first([], 7) == 7 and first([1], 7) == 1


def test_sentinel() -> None:
    assert not MISSING
    assert repr(MISSING) == "MISSING"
    assert isinstance(MISSING, MissingType)


def test_registry_and_chainable() -> None:
    reg: Registry[int] = Registry("number")
    reg.register("one")(1)
    assert reg.get("one") == 1 and list(reg) == ["one"]

    class Counter:
        def __init__(self) -> None:
            self.n = 0

        @chainable
        def bump(self, by: int = 1) -> None:
            self.n += by

    assert Counter().bump().bump(2).n == 3
    assert Counter.bump.__name__ == "bump"


def test_id_factory() -> None:
    ids = IdFactory()
    assert [ids("a"), ids("a"), ids("b")] == ["a1", "a2", "b1"]
    ids.reset()
    assert ids("a") == "a1"


def test_pure_python_fallback() -> None:
    assert _speedups.HAVE_SPEEDUPS is False
    assert _speedups.format_number(2.50) == "2.5"


class TestCli:
    def test_shapes_and_elements(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["shapes"]) == 0
        assert "star" in capsys.readouterr().out
        assert main(["elements"]) == 0
        out = capsys.readouterr().out
        assert "shape: circle ellipse line path polygon polyline rect" in out

    @pytest.mark.parametrize("shape", ["star", "gear", "polygon", "arrow"])
    def test_draw(self, shape: str, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["draw", shape, "--size", "100"]) == 0
        wellformed(capsys.readouterr().out)

    def test_format_and_info(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        source = tmp_path / "in.svg"
        target = tmp_path / "out.svg"
        assert main(["draw", "star", "-o", str(source)]) == 0
        assert main(["format", str(source), "--compact", "--precision", "1", "-o", str(target)]) == 0
        assert target.read_text(encoding="utf-8").count("\n") == 1
        assert main(["info", str(target)]) == 0
        out = capsys.readouterr().out
        assert "polygon" in out and "svg" in out

    def test_module_entry_point(self) -> None:
        result = subprocess.run([sys.executable, "-m", "svgwriter", "--version"], cwd=ROOT, capture_output=True, text=True, check=True)
        assert svg.__version__ in result.stdout


def test_examples_run(tmp_path: Path) -> None:
    examples = sorted((ROOT / "examples").glob("*.py"))
    assert len(examples) >= 3
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    for script in examples:
        result = subprocess.run([sys.executable, str(script), str(tmp_path)], cwd=ROOT, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    outputs = sorted(tmp_path.glob("*.svg"))
    assert len(outputs) >= len(examples)
    for output in outputs:
        wellformed(output.read_text(encoding="utf-8"))


DOCTEST_MODULES = [
    "svgwriter",
    "svgwriter.attributes.length",
    "svgwriter.attributes.style",
    "svgwriter.builder._effects",
    "svgwriter.color.color",
    "svgwriter.document",
    "svgwriter.elements.animation",
    "svgwriter.elements.filters._effects",
    "svgwriter.elements.text",
    "svgwriter.io.writer",
    "svgwriter.path.builder",
    "svgwriter.path.data",
    "svgwriter.transform.matrix",
    "svgwriter.transform.transform",
]


@pytest.mark.parametrize("module_name", DOCTEST_MODULES)
def test_docstring_examples(module_name: str) -> None:
    import doctest

    result = doctest.testmod(importlib.import_module(module_name))
    assert result.attempted > 0
    assert result.failed == 0
