"""The public surface of the stubpy package."""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import stubpy


@pytest.mark.parametrize("name", stubpy.__all__)
def test_all_names_are_importable(name):
    assert hasattr(stubpy, name)
    namespace: dict = {}
    exec(f"from stubpy import {name}", namespace)
    assert namespace[name] is getattr(stubpy, name)


def test_all_has_no_duplicates():
    assert len(stubpy.__all__) == len(set(stubpy.__all__))


def test_metadata():
    assert isinstance(stubpy.__version__, str) and stubpy.__version__
    assert stubpy.__author__ == "Josue N Rivera"


def test_cli_help_exits_cleanly(capsys):
    from stubpy.cli import main

    try:
        rc = main(["--help"])
    except SystemExit as exc:
        rc = exc.code
    assert rc in (0, None)
    assert "usage: stubpy" in capsys.readouterr().out


def test_dunder_main_uses_cli_main():
    from stubpy.cli import main

    module = importlib.import_module("stubpy.__main__")
    assert module.main is main


EXPECTED_ALL = {
    "render", "generate", "check", "Config", "Mode", "load_config", "sync_docstrings",
    "StubResult", "Report", "Diagnostic", "Level", "hint", "extend", "__version__",
}


def test_all_is_the_public_api():
    assert set(stubpy.__all__) == EXPECTED_ALL


@pytest.mark.parametrize("name", [
    "generate_stub", "generate_package", "StubConfig", "ExecutionMode", "PackageResult",
    "DiagnosticLevel", "_ANN_HANDLERS", "generate_class_stub", "StubContext", "ast_harvest",
])
def test_old_names_are_gone(name):
    assert not hasattr(stubpy, name)


@pytest.mark.skipif(sys.platform == "emscripten", reason="no subprocess on Emscripten")
def test_importing_hint_stays_cheap():
    code = (
        "import sys\nfrom stubpy import hint\n"
        "loaded = sorted(m for m in sys.modules if m.startswith('stubpy'))\n"
        "print(loaded, 'inspect' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         cwd=Path(stubpy.__file__).parents[1]).stdout
    assert out.strip() == "['stubpy', 'stubpy._constants', 'stubpy.hint'] False"


def test_lazy_names_are_cached_and_listed():
    assert "generate" in dir(stubpy)
    assert stubpy.generate is stubpy.__dict__["generate"]


def test_version():
    assert stubpy.__version__ == "0.7.0"


def test_hint_namespace():
    assert set(stubpy.hint.__all__) == {"signature", "returns", "ignore"}


def test_extend_namespace():
    from stubpy import extend
    for name in extend.__all__:
        assert getattr(extend, name) is not None
    assert {"register_annotation_handler", "StubContext", "SymbolTable", "ClassSymbol", "FunctionSymbol",
            "Diagnostic", "DiagnosticCollector", "Level", "Stage", "ast_harvest",
            "build_symbol_table"} <= set(extend.__all__)
    assert extend.Level is stubpy.Level
    assert extend.Diagnostic is stubpy.Diagnostic


def test_extend_example_runs():
    from stubpy.extend import ast_harvest, build_symbol_table
    table = build_symbol_table(None, "mymod", ast_harvest("class A: ...\ndef f() -> int: ...\n"))
    assert table.all_names() == ["A", "f"]


def test_public_callables_have_numpy_docstrings():
    import inspect
    for obj in (stubpy.render, stubpy.generate, stubpy.check, stubpy.load_config, stubpy.Config,
                stubpy.sync_docstrings):
        doc = inspect.getdoc(obj) or ""
        assert "Parameters" in doc.splitlines() and "Examples" in doc.splitlines(), obj
