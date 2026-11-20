"""Corpus test: stub real standard-library modules at runtime; every stub must parse cleanly."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import stubpy
from stubpy.config import Config
from stubpy.core.pipeline import render_module
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Level

MODULES = [
    "json", "textwrap", "dataclasses", "enum", "pathlib", "argparse", "logging", "typing",
    "functools", "collections", "string", "csv", "shlex", "difflib", "fractions",
]


def _origin(name: str) -> Path:
    """The source file of *name*, frozen modules included (resolved as ``stubpy.render`` resolves them)."""
    source = stubpy.render(name, config=Config(imports="none")).source
    assert source is not None, name
    return Path(source)


@pytest.mark.parametrize("name", MODULES)
def test_stdlib_module_stubs_cleanly_at_runtime(tmp_path, name):
    ctx = StubContext(config=Config())
    stub = render_module(str(_origin(name)), ctx)
    try:
        ast.parse(stub)
    except SyntaxError as exc:
        pytest.fail(f"{name} stub does not parse: {exc}")
    assert [str(d) for d in ctx.diagnostics if d.level == Level.ERROR] == []
    assert len(stub.splitlines()) > 3


@pytest.mark.parametrize("name", ["json", "logging", "collections"])
def test_stdlib_package_stubs_cleanly_at_runtime(tmp_path, name):
    result = stubpy.generate(name, tmp_path, config=Config())
    assert not result.failed, [(r.module_name, [str(d) for d in r.errors]) for r in result.failed]
    assert all(r.module_name.split(".")[0] == name for r in result)
    for stub in (tmp_path / name).rglob("*.pyi"):
        ast.parse(stub.read_text(encoding="utf-8"))
    assert len(result.written) == len(list((tmp_path / name).rglob("*.pyi")))
