"""Module ``__getattr__`` (PEP 562): lazy names are emitted, and ``__getattr__`` is dropped once all are resolved."""
import ast
import textwrap
from pathlib import Path

import pytest

import stubpy

LAZY_INIT = '''
import importlib

__all__ = ["Canvas", "helper", "sub", "VERSION"]

_LAZY = {"Canvas": ".core", "helper": ".util"}


def __getattr__(name):
    if name in _LAZY:
        return getattr(importlib.import_module(_LAZY[name], __name__), name)
    if name == "sub":
        return importlib.import_module(".sub", __name__)
    if name == "VERSION":
        return "1.0"
    raise AttributeError(name)
'''


def _package(tmp_path: Path, name: str, init: str) -> Path:
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text(textwrap.dedent(init), encoding="utf-8")
    (pkg / "core.py").write_text("class Canvas:\n    def draw(self) -> None: ...\n", encoding="utf-8")
    (pkg / "util.py").write_text("def helper(x: int) -> int:\n    return x\n", encoding="utf-8")
    (pkg / "sub.py").write_text("X = 1\n", encoding="utf-8")
    return pkg / "__init__.py"


@pytest.mark.parametrize("mode", ["runtime", "ast"])
def test_all_names_resolved_drops_getattr(tmp_path, mode):
    init = _package(tmp_path, f"lazy_ok_{mode}", LAZY_INIT)
    text = stubpy.render(init, config=stubpy.Config(mode=mode)).text
    ast.parse(text)
    assert text == (
        "from . import sub as sub\n"
        "from .core import Canvas as Canvas\n"
        "from .util import helper as helper\n"
        "\n"
        '__all__ = ["Canvas", "helper", "sub", "VERSION"]\n'
        "\n"
        "VERSION: str\n"
    )


@pytest.mark.parametrize("mode", ["runtime", "ast"])
def test_unresolved_name_keeps_getattr(tmp_path, mode):
    init = _package(tmp_path, f"lazy_open_{mode}", LAZY_INIT.replace(
        '    raise AttributeError(name)', '    if name == "magic":\n        return _make()\n    raise AttributeError(name)',
    ).replace('"VERSION"]', '"VERSION", "magic"]'))
    result = stubpy.render(init, config=stubpy.Config(mode=mode))
    assert "from .core import Canvas as Canvas" in result.text
    assert "def __getattr__(name)" in result.text
    assert any("magic" in d.message for d in result.diagnostics)


def test_getattr_without_raise_is_kept(tmp_path):
    init = _package(tmp_path, "lazy_fallthrough", '''
        def __getattr__(name):
            if name == "Canvas":
                from .core import Canvas
                return Canvas
            return globals().get("_" + name)
    ''')
    text = stubpy.render(init).text
    assert "from .core import Canvas as Canvas" in text
    assert "def __getattr__(name)" in text


def test_runtime_resolves_names_the_source_cannot(tmp_path):
    init = _package(tmp_path, "lazy_runtime", '''
        import importlib
        __all__ = ["Canvas"]
        _where = ".co" + "re"
        def __getattr__(name):
            if name in __all__:
                return getattr(importlib.import_module(_where, __name__), name)
            raise AttributeError(name)
    ''')
    runtime = stubpy.render(init).text
    assert "from .core import Canvas as Canvas" in runtime and "__getattr__" not in runtime
    static = stubpy.render(init, config=stubpy.Config(mode="ast")).text
    assert "def __getattr__(name)" in static


@pytest.mark.parametrize("mode", ["runtime", "ast"])
def test_lazy_names_imported_under_type_checking_drop_getattr(tmp_path, mode):
    init = _package(tmp_path, f"lazy_tc_{mode}", '''
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from .core import Canvas
        __all__ = ["Canvas"]
        _LAZY = {"Canvas": ("core", "Canvas")}
        def __getattr__(name):
            if name in _LAZY:
                module_name, attribute = _LAZY[name]
                return getattr(importlib.import_module(f".{module_name}", __name__), attribute)
            raise AttributeError(name)
    ''')
    text = stubpy.render(init, config=stubpy.Config(mode=mode)).text
    assert "from .core import Canvas as Canvas" in text and "__getattr__" not in text
