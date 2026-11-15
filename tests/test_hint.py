"""The stubpy.hint decorators: runtime behaviour, and how both execution modes honour them."""
from __future__ import annotations

import functools

import pytest

import stubpy
from stubpy import hint
from stubpy.analysis.harvest import ast_harvest
from stubpy.analysis.hints import is_ignored, live_hint, returns_hint, signature_hint
from stubpy.config import Config
from tests.conftest import assert_valid_syntax, make_stub_ctx

MODES = ["runtime", "ast"]


class TestDecoratorsAtRuntime:
    def test_return_the_same_object(self):
        def f(x):
            return x
        assert hint.signature("(x: int) -> int")(f) is f
        assert hint.returns("int")(f) is f
        assert hint.ignore(f) is f
        assert f(3) == 3

    def test_attributes(self):
        @hint.signature(" (x: int) -> int ")
        @hint.returns("int")
        def f(x):
            return x
        assert f.__stubpy_signature__ == "(x: int) -> int"
        assert f.__stubpy_returns__ == "int"
        assert not hasattr(f, "__stubpy_ignore__")

    def test_ignore_on_class(self):
        @hint.ignore
        class C:
            pass
        assert C.__stubpy_ignore__ is True

    def test_objects_without_attributes_are_returned_unchanged(self):
        assert hint.ignore(len) is len
        assert hint.signature("(obj) -> int")(len) is len

    def test_signature_validation(self):
        with pytest.raises(TypeError):
            hint.signature(42)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="start with"):
            hint.signature("x: int")
        with pytest.raises(TypeError):
            hint.returns(int)  # type: ignore[arg-type]

    def test_wraps_and_descriptors_are_followed(self):
        @hint.returns("str")
        def inner():
            pass

        @functools.wraps(inner)
        def outer():
            pass

        assert live_hint(outer, "__stubpy_returns__") == "str"
        assert returns_hint(staticmethod(inner)) == "str"
        assert returns_hint(property(inner)) == "str"
        assert returns_hint(functools.partial(inner)) == "str"

    def test_class_attribute_lookup_does_not_walk_members(self):
        class C:
            @hint.ignore
            def func(self):
                pass
        assert not is_ignored(C)


class TestSyntacticRecognition:
    def test_spellings(self):
        source = (
            "import stubpy\n"
            "import stubpy as sp\n"
            "from stubpy import hint as h\n"
            "from stubpy.hint import signature as sig, ignore\n"
            "@stubpy.hint.signature('(a: int) -> int')\n"
            "def a(a): ...\n"
            "@sp.hint.returns('str')\n"
            "def b(): ...\n"
            "@h.ignore\n"
            "def c(): ...\n"
            "@sig('(d: float) -> float')\n"
            "def d(d): ...\n"
            "@ignore\n"
            "def e(): ...\n"
            "@hint.ignore()\n"
            "def f(): ...\n"
        )
        fns = {f.name: f for f in ast_harvest(source).functions}
        assert fns["a"].hint_signature == "(a: int) -> int"
        assert fns["b"].hint_returns == "str"
        assert fns["c"].hint_ignore and fns["e"].hint_ignore and fns["f"].hint_ignore
        assert fns["d"].hint_signature == "(d: float) -> float"
        assert all(f.decorators == [] for f in fns.values())

    def test_unrelated_decorators_kept(self):
        source = "import functools\n@functools.lru_cache\n@other.hint.ignore\ndef g(): ...\n"
        fn = ast_harvest(source).functions[0]
        assert fn.decorators == ["functools.lru_cache", "other.hint.ignore"]
        assert not fn.hint_ignore

    def test_non_literal_argument_strips_but_ignores(self):
        fn = ast_harvest("from stubpy import hint\n@hint.signature(SIG)\ndef g(): ...\n").functions[0]
        assert fn.decorators == []
        assert fn.hint_signature is None

    def test_class_ignore_and_signature_lookup(self):
        syms = ast_harvest("from stubpy import hint\n@hint.ignore\nclass K: ...\n")
        assert syms.classes[0].hint_ignore
        assert syms.classes[0].decorators == []
        assert signature_hint(None, syms.classes[0]) is None


SOURCE = '''
from stubpy import hint

@hint.signature("(x: float, y: float) -> float")
def dist(*args, **kwargs):
    return 0.0

@hint.returns("list[int]")
def evens(n: int):
    return list(range(0, n, 2))

@hint.ignore
def _debug_only(): ...

@hint.ignore
def public_but_hidden(): ...

@hint.ignore
class Internal:
    pass

class Shape:
    @hint.signature("(self, scale: float = ...) -> Shape")
    def grow(self, *a, **k):
        return self

    @hint.returns("float")
    def area(self):
        return 0.0

    @hint.ignore
    def debug(self): ...

    @staticmethod
    @hint.signature("(a: int, b: int) -> int")
    def add(*args): ...

    @hint.ignore
    class Nested:
        pass

    def keep(self) -> None: ...
'''


@pytest.mark.parametrize("mode", MODES)
class TestPipelineHonoursHints:
    def _stub(self, mode, **cfg):
        stub, ctx = make_stub_ctx(SOURCE, mode, **cfg)
        assert not ctx.diagnostics.has_errors()
        return stub

    def test_signature_override(self, mode):
        stub = self._stub(mode)
        assert "def dist(x: float, y: float) -> float: ..." in stub
        assert "def grow(self, scale: float = ...) -> Shape: ..." in stub

    def test_signature_on_staticmethod(self, mode):
        stub = self._stub(mode)
        assert "@staticmethod\n    def add(a: int, b: int) -> int: ..." in stub

    def test_returns_override(self, mode):
        stub = self._stub(mode)
        assert "def evens(n: int) -> list[int]: ..." in stub
        assert "def area(self) -> float: ..." in stub

    def test_ignore(self, mode):
        stub = self._stub(mode, include_private=True)
        for name in ("_debug_only", "public_but_hidden", "Internal", "def debug", "Nested"):
            assert name not in stub
        assert "def keep(self) -> None: ..." in stub

    def test_hint_decorators_not_emitted(self, mode):
        stub = self._stub(mode)
        assert "hint" not in stub
        assert "stubpy" not in stub
        assert_valid_syntax(stub)

    def test_include_docstrings_with_signature(self, mode):
        source = 'from stubpy import hint\n@hint.signature("(x: int) -> int")\ndef f(x):\n    """Doc."""\n'
        stub, _ = make_stub_ctx(source, mode, include_docstrings=True)
        assert "def f(x: int) -> int:" in stub


class TestRuntimeOnlyHints:
    def test_hint_set_dynamically_is_seen_at_runtime(self, tmp_path):
        src = tmp_path / "dyn.py"
        src.write_text(
            "from stubpy import hint\n"
            "deco = hint.signature('(n: int) -> int')\n"
            "@deco\n"
            "def built(*args):\n"
            "    return 1\n"
            "def plain(*args):\n    return 1\n"
            "plain = hint.ignore(plain)\n"
        )
        runtime = stubpy.render(src).text
        assert "def built(n: int) -> int: ..." in runtime
        assert "plain" not in runtime
        ast_only = stubpy.render(src, config=Config(mode="ast")).text
        assert "def built(*args)" in ast_only

    def test_invalid_signature_text_falls_back_with_warning(self, tmp_path):
        src = tmp_path / "bad.py"
        src.write_text("def f(x: int) -> int: ...\nf.__stubpy_signature__ = '(x: int'\n")
        result = stubpy.render(src)
        assert "def f(x: int) -> int: ..." in result.text
        assert any("hint.signature" in d.message for d in result.warnings)

    def test_names_in_hint_get_imported(self, tmp_path):
        src = tmp_path / "imp.py"
        src.write_text(
            "from decimal import Decimal\n"
            "from stubpy import hint\n"
            "@hint.signature('(x: Decimal) -> Decimal')\n"
            "def f(x): return x\n"
        )
        for mode in MODES:
            text = stubpy.render(src, config=Config(mode=mode)).text
            assert "from decimal import Decimal" in text
            assert "import hint" not in text
