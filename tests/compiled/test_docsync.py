"""Docstring sync into hand-written stubs: only docstrings change, every other byte stays."""
from __future__ import annotations

import ast
import sys
import textwrap
import types

import pytest

import stubpy
from stubpy.cli import main
from stubpy.compiled.docsync import sibling_module_file, sync_docstrings
from stubpy.compiled.docsync._edit import apply_edits, plan_edits

from .fakes import fake_module

STUB = textwrap.dedent('''\
    # hand-written; keep this comment
    from typing import overload

    def area(points, /) -> float: ...  # trailing comment

    def lerp(a: float, b: float, t: float = 0.5) -> float:
        """Stale text."""

    @overload
    def blur(img, std_x: float, std_y: float): ...
    @overload
    def blur(img, std: float): ...

    class Widget:
        def resize(self, w: int, h: int) -> "Widget":
            ...

        @property
        def width(self) -> int: ...

        class Kind:
            def clear(self) -> None: ...

    def not_in_module() -> None: ...
''')


def _sync(text: str, module: types.ModuleType) -> tuple[str, list[str]]:
    from stubpy.compiled.docsync._discover import runtime_docstring

    edits = plan_edits(text, lambda path, _node: runtime_docstring(module, path))
    return apply_edits(text, edits), [e.name for e in edits]


def _without_docstrings(text: str) -> str:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Expr(ast.Constant(...))]
        elif isinstance(body, list) and len(body) == 1 and isinstance(body[0], ast.Pass):
            node.body = [ast.Expr(ast.Constant(...))]
    return ast.dump(tree)


class TestEdits:
    def test_docstrings_are_inserted_and_replaced(self):
        text, names = _sync(STUB, fake_module())
        assert set(names) == {"area", "lerp", "Widget", "Widget.resize", "Widget.width", "Widget.Kind"}
        assert 'def area(points, /) -> float:\n    """Shoelace area."""  # trailing comment' in text
        assert '"""Interpolate."""' in text and "Stale text" not in text
        assert '    def width(self) -> int:\n        """Width in pixels."""' in text
        assert 'class Widget:\n    """A widget."""\n' in text

    def test_everything_else_is_kept(self):
        text, _ = _sync(STUB, fake_module())
        assert "# hand-written; keep this comment" in text
        assert "def blur(img, std: float): ..." in text
        assert "def not_in_module() -> None: ..." in text
        assert _without_docstrings(text) == _without_docstrings(STUB)

    def test_up_to_date_stub_needs_no_edits(self):
        text, _ = _sync(STUB, fake_module())
        again, names = _sync(text, fake_module())
        assert names == [] and again == text

    def test_crlf_and_non_ascii_survive(self):
        crlf = STUB.replace("# hand-written", "# é hand-written").replace("\n", "\r\n")
        text, _ = _sync(crlf, fake_module())
        assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
        assert "# é hand-written" in text

    def test_overload_variants_are_untouched(self):
        text, names = _sync(STUB, fake_module())
        assert "blur" not in names
        assert text.count('"""') == 2 * len(names)


class TestSyncDocstrings:
    def test_writes_and_reports(self, tmp_path):
        stub = tmp_path / "fakeext.pyi"
        stub.write_bytes(STUB.encode())
        result = sync_docstrings(stub, fake_module())
        assert result.written and result.changed and result.module == "fakeext"
        assert stub.read_text(encoding="utf-8") == result.text
        assert not sync_docstrings(stub, fake_module()).changed

    def test_check_mode_does_not_write(self, tmp_path):
        stub = tmp_path / "fakeext.pyi"
        stub.write_bytes(STUB.encode())
        result = stubpy.sync_docstrings(stub, fake_module(), write=False)
        assert result.changed and not result.written
        assert stub.read_bytes() == STUB.encode()

    def test_missing_stub(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            sync_docstrings(tmp_path / "nope.pyi", fake_module())


class TestDiscovery:
    def test_same_stem_sibling(self, tmp_path):
        stub = tmp_path / "_x.pyi"
        stub.write_text("")
        assert sibling_module_file(stub) is None
        (tmp_path / "_x.pyx").write_text("")
        assert sibling_module_file(stub) == tmp_path / "_x.pyx"
        (tmp_path / "_xy.py").write_text("")
        assert sibling_module_file(stub) == tmp_path / "_x.pyx"


@pytest.fixture
def pure_pair(tmp_path, monkeypatch):
    """A module ``_dsync_mod.py`` and a hand-written ``_dsync_mod.pyi`` beside it."""
    (tmp_path / "_dsync_mod.py").write_text('def f(x):\n    """Runtime doc."""\n', encoding="utf-8")
    stub = tmp_path / "_dsync_mod.pyi"
    stub.write_text("def f(x) -> int: ...\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    yield stub
    sys.modules.pop("_dsync_mod", None)


class TestCli:
    def test_check_then_sync(self, pure_pair, capsys):
        assert main(["docstrings", "check", str(pure_pair)]) == 1
        assert "stale" in capsys.readouterr().out
        assert main(["docstrings", "sync", str(pure_pair)]) == 0
        assert '"""Runtime doc."""' in pure_pair.read_text(encoding="utf-8")
        assert main(["docstrings", "check", str(pure_pair)]) == 0

    def test_module_option(self, pure_pair):
        assert main(["docstrings", "check", "-m", "_dsync_mod"]) == 1

    def test_folder(self, pure_pair):
        assert main(["docstrings", "check", str(pure_pair.parent)]) == 1

    def test_import_error_exits_2(self, tmp_path, capsys):
        stub = tmp_path / "_dsync_missing.pyi"
        stub.write_text("def f() -> None: ...\n")
        assert main(["docstrings", "check", str(stub)]) == 2
        assert main(["docstrings", "check", "-m", "no_such_module_for_stubpy_xyz"]) == 2

    def test_nothing_to_do_is_a_usage_error(self):
        assert main(["docstrings", "sync"]) == 2


def test_docstring_goes_above_a_decorated_first_member():
    module = fake_module()
    stub = "class Widget:\n    @property\n    def width(self) -> int: ...\n"
    text, names = _sync(stub, module)
    assert text.startswith('class Widget:\n    """A widget."""\n    @property\n')
    ast.parse(text)


def test_property_setter_gets_no_docstring():
    stub = ("class Widget:\n    @property\n    def width(self) -> int: ...\n"
            "    @width.setter\n    def width(self, value: int) -> None: ...\n")
    text, names = _sync(stub, fake_module())
    assert names.count("Widget.width") == 1
    assert "def width(self, value: int) -> None: ...\n" in text
