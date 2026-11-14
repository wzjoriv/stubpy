"""Edge cases: every generated stub is valid, UTF-8 and deterministic."""
from __future__ import annotations

import ast

import pytest

from stubpy import generate_package
from stubpy.config import ExecutionMode, StubConfig
from tests.conftest import make_stub_ctx, write_tree

MODES = ["runtime", "ast_only"]

DOCSTRING_SOURCE = r'''
def quoted() -> None:
    """Has \"\"\" inside and ends with a quote: "x\""""
def slashed() -> None:
    """Ends with a backslash \\"""
class Doc:
    r"""Raw C:\path\name and \n literal."""
    def m(self) -> None:
        """Line one.

        Line two with \"\"\"."""
'''


@pytest.mark.parametrize("mode", MODES)
def test_docstrings_with_triple_quotes_and_backslashes(mode):
    stub, ctx = make_stub_ctx(DOCSTRING_SOURCE, mode, include_docstrings=True)
    assert not ctx.diagnostics.has_errors()
    tree = ast.parse(stub)
    docs = [ast.get_docstring(n, clean=False) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(n)]
    if mode == "runtime":
        assert 'Has """ inside and ends with a quote: "x"' in docs
        assert "Ends with a backslash \\" in docs
        assert any("C:\\path\\name and \\n literal." in d for d in docs)


@pytest.mark.parametrize("mode", MODES)
def test_stub_files_are_utf8(tmp_path, mode):
    pkg = tmp_path / "edgepkg_utf8"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "naïve.py").write_text("def grüß(größe: str = 'ß') -> str: ...\n", encoding="utf-8")
    out = tmp_path / "out"
    result = generate_package(pkg, out, config=StubConfig(execution_mode=ExecutionMode(mode)))
    assert not result.failed
    text = (out / "naïve.pyi").read_bytes().decode("utf-8")
    assert "def grüß(größe: str = 'ß') -> str" in text


DETERMINISM_PACKAGE = {
    "edgepkg_det/__init__.py": """
        from .shapes import Base, Child
        from .colors import Mode
        __all__ = ['Base', 'Child', 'Mode']
    """,
    "edgepkg_det/colors.py": """
        from enum import Enum, Flag, auto
        from typing import ClassVar, Literal, Optional, Union
        class Mode(Enum):
            FAST = 1
            SLOW = 2
        class Bits(Flag):
            A = auto()
            B = auto()
        def pick(m: Mode = Mode.FAST, kind: Literal['a', 'b'] = 'a') -> Optional[Union[int, str]]: ...
    """,
    "edgepkg_det/shapes.py": """
        from dataclasses import dataclass, field
        from typing import ClassVar
        from .colors import Mode
        @dataclass
        class Base:
            mode: Mode = Mode.SLOW
            tags: list[str] = field(default_factory=list)
            kind: ClassVar[str] = "base"
        class Child(Base):
            def __init__(self, label: str, *args, size: int = 1, **kwargs) -> None:
                super().__init__(*args, **kwargs)
    """,
}


@pytest.mark.parametrize("mode", ["runtime", "ast_only", "auto"])
def test_package_output_is_deterministic(tmp_path, mode):
    pkg = write_tree(tmp_path / "proj", DETERMINISM_PACKAGE) / "edgepkg_det"
    cfg = StubConfig(execution_mode=ExecutionMode(mode))
    runs = []
    for i in range(2):
        out = tmp_path / f"run{i}"
        result = generate_package(pkg, out, config=cfg)
        assert not result.failed
        runs.append({p.relative_to(out).as_posix(): p.read_text(encoding="utf-8") for p in out.rglob("*.pyi")})
    assert runs[0] == runs[1]
    assert len(runs[0]) == 3
