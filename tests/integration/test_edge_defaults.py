"""Edge cases: default values always render as a valid literal, an in-scope name or ``...``."""
from __future__ import annotations

import ast
import re

import stubpy
from stubpy.config import Config
from tests.conftest import flatten, make_stub_ctx, write_tree


def _no_repr_leak(stub: str) -> None:
    assert " at 0x" not in stub
    assert not re.search(r"=\s*<", stub)


def _param(stub: str, name: str) -> str:
    """Return parameter *name* of the last function in *stub* as ``name: ann = default``."""
    func = [n for n in ast.walk(ast.parse(stub)) if isinstance(n, ast.FunctionDef)][-1]
    args = func.args
    positional = args.posonlyargs + args.args
    defaults = dict(zip([a.arg for a in positional[len(positional) - len(args.defaults):]], args.defaults, strict=True))
    defaults.update({a.arg: d for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True) if d is not None})
    for arg in positional + args.kwonlyargs:
        if arg.arg == name:
            text = name + (f": {ast.unparse(arg.annotation)}" if arg.annotation else "")
            return text + (f" = {ast.unparse(defaults[name])}" if name in defaults else "")
    raise AssertionError(f"parameter {name!r} not in: {stub}")


class TestDefaults:
    def test_sentinel_object_becomes_ellipsis(self):
        stub, _ = make_stub_ctx("""
            _MISSING = object()
            def f(x=_MISSING): ...
        """)
        assert _param(stub, "x").endswith("= ...")
        _no_repr_leak(stub)

    def test_infinities_and_nan_become_ellipsis(self):
        stub, _ = make_stub_ctx("""
            import math
            def f(a=float("inf"), b=-float("inf"), c=float("nan"), d=math.inf): ...
        """)
        for name in "abc":
            assert _param(stub, name).endswith("= ..."), stub
        assert _param(stub, "d").endswith(("= ...", "= math.inf"))
        assert not re.search(r"=\s*-?(inf|nan)\b", stub)

    def test_huge_int_is_not_converted_to_text(self):
        stub, _ = make_stub_ctx("""
            def f(x=10**5000, y=7): ...
        """)
        assert _param(stub, "x").endswith("= ...")
        assert _param(stub, "y").endswith("= 7")

    def test_string_with_both_quote_kinds_round_trips(self):
        stub, _ = make_stub_ctx('''
            def f(s='it\\'s "quoted"', b=b"x'\\"y"): ...
        ''')
        call = ast.parse(flatten(stub)).body[-1]
        defaults = [ast.literal_eval(d) for d in call.args.defaults]
        assert defaults == ['it\'s "quoted"', b"x'\"y"]

    def test_class_attribute_and_module_constant_defaults(self):
        stub, _ = make_stub_ctx("""
            DEFAULT_T = 5.0
            class Config:
                LIMIT = 10
            def f(a=Config.LIMIT, b=DEFAULT_T): ...
        """)
        assert "Config.LIMIT" not in stub.split("def f")[1]
        assert "= DEFAULT_T" not in stub

    def test_imported_module_attribute_default_is_kept_with_import(self):
        stub, _ = make_stub_ctx("""
            import os
            def f(sep=os.sep): ...
        """)
        assert _param(stub, "sep") == "sep: str = os.sep"
        assert "import os" in stub

    def test_enum_member_default_in_same_module(self):
        stub, _ = make_stub_ctx("""
            from enum import Enum
            class Mode(Enum):
                FAST = 1
                SLOW = 2
            def run(mode: Mode = Mode.FAST) -> None: ...
        """)
        assert _param(stub, "mode") == "mode: Mode = Mode.FAST"

    def test_mutable_defaults(self):
        stub, _ = make_stub_ctx("""
            def f(a=[], b={}, c=(), d=set(), e=[1, "x"], f={"k": (1, 2)}): ...
        """)
        assert _param(stub, "a").endswith("= []")
        assert _param(stub, "b").endswith("= {}")
        assert _param(stub, "c").endswith("= ()")
        assert _param(stub, "d").endswith("= ...")
        assert _param(stub, "e").endswith("= [1, 'x']")
        assert _param(stub, "f").endswith("= {'k': (1, 2)}")


class TestEnumDefaultsAcrossModules:
    def test_imported_enum_default_gets_its_import(self, tmp_path):
        pkg = write_tree(tmp_path / "proj", {
            "edgepkg_enumdef/__init__.py": "",
            "edgepkg_enumdef/modes.py": """
                from enum import Enum
                class Mode(Enum):
                    FAST = "fast"
            """,
            "edgepkg_enumdef/run.py": """
                from .modes import Mode
                def run(mode=Mode.FAST): ...
            """,
        })
        out = tmp_path / "out"
        result = stubpy.generate(pkg, out, config=Config())
        assert not result.failed
        stub = (out / "edgepkg_enumdef" / "run.pyi").read_text(encoding="utf-8")
        ast.parse(stub)
        assert "mode" in stub and "Mode.FAST" in stub
        assert re.search(r"^from (\.modes|edgepkg_enumdef\.modes) import Mode$", stub, re.M), stub


class TestKnownBugDataclassEnumDefault:
    def test_dataclass_init_enum_default_is_member_name(self):
        stub, _ = make_stub_ctx("""
            from dataclasses import dataclass
            from enum import Enum
            class Mode(Enum):
                RUNTIME = "runtime"
            @dataclass
            class Config:
                mode: Mode = Mode.RUNTIME
                label: str = 'it\\'s "x"'
        """)
        assert "mode: Mode = Mode.RUNTIME" in stub
        _no_repr_leak(stub)

    def test_dataclass_sentinel_and_factory_defaults(self):
        stub, _ = make_stub_ctx("""
            from dataclasses import dataclass, field
            _UNSET = object()
            @dataclass
            class Box:
                tag: object = _UNSET
                items: list = field(default_factory=list)
        """)
        flat = flatten(stub)
        assert "tag: object = ..." in flat
        assert "items: list = ..." in flat
        _no_repr_leak(stub)

    def test_namedtuple_enum_default(self):
        stub, _ = make_stub_ctx("""
            from enum import IntEnum
            from typing import NamedTuple
            class Level(IntEnum):
                LOW = 1
            class Item(NamedTuple):
                level: Level = Level.LOW
                ratio: float = float("nan")
        """)
        assert "level: Level = Level.LOW" in stub
        assert "ratio: float = ..." in stub

    def test_literal_of_enum_member(self):
        stub, _ = make_stub_ctx("""
            from enum import Enum
            from typing import Literal
            class Color(Enum):
                RED = 1
            def paint(c: Literal[Color.RED, "x"]) -> None: ...
        """)
        assert "Literal[Color.RED, 'x']" in stub
