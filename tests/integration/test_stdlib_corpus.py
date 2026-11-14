"""Corpus test: stub real standard-library modules at runtime; every stub must parse cleanly."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from stubpy import generate_package, generate_stub
from stubpy.config import ExecutionMode, StubConfig
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import DiagnosticLevel

MODULES = [
    "json", "textwrap", "dataclasses", "enum", "pathlib", "argparse", "logging", "typing",
    "functools", "collections", "string", "csv", "shlex", "difflib", "fractions",
]


def _origin(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    assert spec is not None and spec.origin, name
    return Path(spec.origin)


@pytest.mark.parametrize("name", MODULES)
def test_stdlib_module_stubs_cleanly_at_runtime(tmp_path, name):
    ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.RUNTIME))
    stub = generate_stub(str(_origin(name)), str(tmp_path / f"{name}.pyi"), ctx=ctx)
    try:
        ast.parse(stub)
    except SyntaxError as exc:
        pytest.fail(f"{name} stub does not parse: {exc}")
    assert [str(d) for d in ctx.diagnostics if d.level == DiagnosticLevel.ERROR] == []
    assert len(stub.splitlines()) > 3


@pytest.mark.parametrize("name", ["json", "logging", "collections"])
def test_stdlib_package_stubs_cleanly_at_runtime(tmp_path, name):
    root = _origin(name).parent
    contexts: list[StubContext] = []

    def factory() -> StubContext:
        ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.RUNTIME))
        contexts.append(ctx)
        return ctx

    result = generate_package(root, tmp_path / name, ctx_factory=factory)
    assert not result.failed, [(p.name, [str(d) for d in diags]) for p, diags in result.failed]
    for stub in (tmp_path / name).rglob("*.pyi"):
        ast.parse(stub.read_text(encoding="utf-8"))
    assert [str(d) for c in contexts for d in c.diagnostics if d.level == DiagnosticLevel.ERROR] == []
