"""End-to-end forwarding across Python versions and options."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.conftest import assert_valid_syntax


class TestVersionCompatibility:
    """Ensure annotation handling is robust across Python versions."""

    def test_builtin_list_subscript_direct(self):
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext()
        assert annotation_to_str(list[int], ctx) == "list[int]"

    def test_builtin_tuple_variadic_direct(self):
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext()
        assert annotation_to_str(tuple[int, ...], ctx) == "tuple[int, ...]"

    def test_builtin_dict_subscript_direct(self):
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext()
        assert annotation_to_str(dict[str, int], ctx) == "dict[str, int]"

    def test_nested_builtin_generics(self):
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext()
        assert annotation_to_str(list[tuple[int, str]], ctx) == "list[tuple[int, str]]"

    def test_union_legacy_mode_emits_Union_not_pipe(self):
        """In legacy mode, Union[str, int] must emit Union[str, int] not str | int."""
        import typing

        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        union_type = typing.Union[str, int]
        result = annotation_to_str(union_type, ctx)
        assert result == "Union[str, int]", f"Expected Union[str, int], got {result!r}"

    def test_union_legacy_optional_emits_Optional(self):
        """In legacy mode, Union[str, None] must emit Optional[str]."""
        import typing

        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        result = annotation_to_str(typing.Union[str, None], ctx)
        assert result == "Optional[str]", f"Got {result!r}"

    def test_pep604_union_legacy_mode(self):
        """str | int (runtime UnionType) in legacy mode emits Union[str, int]."""
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        result = annotation_to_str(str | int, ctx)
        assert result == "Union[str, int]", f"Got {result!r}"

    def test_pep604_union_modern_mode(self):
        """str | int in modern mode emits str | int."""
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        ctx = StubContext(config=StubConfig(union_style="modern"))
        result = annotation_to_str(str | int, ctx)
        assert result == "str | int", f"Got {result!r}"

    def test_dataclass_annotations_resolved_via_get_type_hints(self):
        """Dataclass field annotations are resolved via get_type_hints (3.14 compat)."""
        from dataclasses import dataclass

        from stubpy.core.context import StubContext
        from stubpy.emit import generate_class_stub

        @dataclass
        class Point:
            x: float
            y: float = 0.0

        ctx = StubContext()
        stub = generate_class_stub(Point, ctx)
        assert "x: float" in stub
        assert "y: float" in stub
        assert "def __init__" in stub
        init_part = stub.split("def __init__")[1]
        assert "x: float" in init_part

    def test_typeddict_fields_resolved_via_get_type_hints(self):
        """TypedDict fields are resolved via get_type_hints (3.14 compat)."""
        from typing import TypedDict

        from stubpy.core.context import StubContext
        from stubpy.emit import generate_class_stub

        class Config(TypedDict):
            host: str
            port: int

        ctx = StubContext()
        stub = generate_class_stub(Config, ctx)
        assert "host: str" in stub
        assert "port: int" in stub
        assert "..." not in stub

    def test_get_type_hints_with_builtins_fallback(self):
        """get_type_hints succeeds even when __globals__ lacks builtins."""
        from stubpy.resolve.hints import get_hints_for_method

        def fn() -> "list[int]": ...
        orig = fn.__globals__.get("__builtins__")
        fn.__globals__["__builtins__"] = {}
        try:
            result = get_hints_for_method(fn)
            assert isinstance(result, dict)
        finally:
            if orig is None:
                fn.__globals__.pop("__builtins__", None)
            else:
                fn.__globals__["__builtins__"] = orig


class TestDemoDispatchStub:
    """End-to-end tests against demo/dispatch.py."""

    @pytest.fixture(scope="class")
    @classmethod
    def dispatch_stub(cls, tmp_path_factory):
        root = Path(__file__).resolve().parents[2]
        tmp = tmp_path_factory.mktemp("dispatch")
        from stubpy import generate_stub
        from stubpy.core.context import StubContext
        ctx = StubContext()
        stub = generate_stub(
            str(root / "demo" / "dispatch.py"),
            str(tmp / "dispatch.pyi"),
            ctx=ctx,
        )
        return stub

    def test_syntax_valid(self, dispatch_stub):
        assert_valid_syntax(dispatch_stub)

    def test_property_mro_setter_present(self, dispatch_stub):
        """ColoredSVGRenderer overrides getter only — setter must come from MRO."""
        assert "class ColoredSVGRenderer" in dispatch_stub
        after = dispatch_stub.split("class ColoredSVGRenderer")[1]
        assert "@color.setter" in after.split("class ")[0]

    def test_cross_file_tint_expanded(self, dispatch_stub):
        """CrossFileRenderer.tint expands make_color params (r, g, b, a)."""
        after = dispatch_stub.split("class CrossFileRenderer")[1]
        tint = after.split("def tint")[1].split("def ")[0]
        assert "r: float" in tint
        assert "g: float" in tint
        assert "b: float" in tint
        assert "a: float" in tint

    def test_multiformat_renderer_union(self, dispatch_stub):
        """MultiFormatRenderer.render gets union of svg and png params."""
        assert "class MultiFormatRenderer" in dispatch_stub
        after = dispatch_stub.split("class MultiFormatRenderer")[1]
        render = after.split("def render")[1].split("def ")[0]
        assert "compress: bool" in render
        assert "dpi: int" in render
        assert "width: int" in render

    def test_nested_isolation_no_save_svg_params(self, dispatch_stub):
        """IsolatedDispatcher.dispatch must NOT expand save_svg's params."""
        assert "class IsolatedDispatcher" in dispatch_stub
        after = dispatch_stub.split("class IsolatedDispatcher")[1]
        dispatch = after.split("def dispatch")[1].split("def ")[0]
        assert "compress: bool" not in dispatch
        assert "dpi: int" not in dispatch


class TestIncrementalModeDemo:
    """Test incremental update with demo files."""

    def test_incremental_preserves_manual_content(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\ny: str = 'hello'\n")
        pyi = tmp_path / "mod.pyi"

        from stubpy import generate_stub
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        from stubpy.merge import BEGIN_MARKER

        ctx1 = StubContext(config=StubConfig(incremental_update=True))
        generate_stub(str(src), str(pyi), ctx=ctx1)
        content1 = pyi.read_text()
        assert BEGIN_MARKER in content1

        pyi.write_text(f"# MyCustomClass = ...  # manual\n{content1}")

        src.write_text("z: float = 3.14\n")
        ctx2 = StubContext(config=StubConfig(incremental_update=True))
        generate_stub(str(src), str(pyi), ctx=ctx2)
        content2 = pyi.read_text()
        assert "# MyCustomClass" in content2
        assert "z: float" in content2
        assert_valid_syntax(content2)


class TestResolveKwargsFlag:
    """``resolve_kwargs=False`` / ``--no-resolve-kwargs`` keeps **kwargs as-is."""

    def test_kwargs_preserved_when_flag_false(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class Base:\n"
            "    def __init__(self, color: str, size: float = 1.0) -> None: ...\n\n"
            "class Child(Base):\n"
            "    def __init__(self, label: str, **kwargs) -> None: ...\n"
        )
        from stubpy import generate_stub
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        ctx = StubContext(config=StubConfig(resolve_kwargs=False))
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        child_part = stub.split("class Child")[1]
        assert "**kwargs" in child_part
        assert "color" not in child_part
        assert "size" not in child_part

    def test_kwargs_expanded_by_default(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class Base:\n"
            "    def __init__(self, color: str, size: float = 1.0) -> None: ...\n\n"
            "class Child(Base):\n"
            "    def __init__(self, label: str, **kwargs) -> None: ...\n"
        )
        from stubpy import generate_stub
        from stubpy.core.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        child_part = stub.split("class Child")[1]
        assert "color: str" in child_part
        assert "size: float" in child_part

    def test_resolve_kwargs_false_in_toml(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "mod.py").write_text(
            "class A:\n"
            "    def f(self, x: int = 1) -> None: ...\n\n"
            "class B(A):\n"
            "    def f(self, **kwargs) -> None: ...\n"
        )
        (pkg / "stubpy.toml").write_text("resolve_kwargs = false\n")
        sys.argv = ["stubpy", str(pkg), "-o", str(tmp_path / "stubs")]
        from stubpy.cli import main
        main()
        stub = (tmp_path / "stubs" / "mod.pyi").read_text()
        b_part = stub.split("class B")[1]
        assert "**kwargs" in b_part

    def test_cli_no_resolve_kwargs_flag(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class A:\n"
            "    def f(self, x: int, y: str = 'a') -> None: ...\n\n"
            "class B(A):\n"
            "    def f(self, **kwargs) -> None: ...\n"
        )
        sys.argv = ["stubpy", str(src), "--no-resolve-kwargs"]
        from stubpy.cli import main
        main()
        stub = src.with_suffix(".pyi").read_text()
        b_part = stub.split("class B")[1]
        assert "**kwargs" in b_part
        assert "x: int" not in b_part

    def test_resolve_args_false(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "def process(*items: str, gamma: float = 1.0) -> list: ...\n\n"
            "def batch(*items: str, **opts) -> list:\n"
            "    return process(*items, **opts)\n"
        )
        from stubpy import generate_stub
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        ctx = StubContext(config=StubConfig(resolve_args=False))
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        batch_part = stub.split("def batch")[1]
        assert "*items" in batch_part

    def test_typeshed_style_both_flags_false(self, tmp_path):
        """With both flags False, stub is plain **kwargs / *args (typeshed convention)."""
        src = tmp_path / "mod.py"
        src.write_text(
            "class Base:\n"
            "    def run(self, speed: float, *items: str, verbose: bool = False) -> None: ...\n\n"
            "class Child(Base):\n"
            "    def run(self, *args, **kwargs) -> None: ...\n"
        )
        from stubpy import generate_stub
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        ctx = StubContext(config=StubConfig(resolve_kwargs=False, resolve_args=False))
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        child_part = stub.split("class Child")[1]
        assert "*args" in child_part
        assert "**kwargs" in child_part
        assert "speed" not in child_part


class TestTypeInferenceFromDefaults:
    """Unannotated parameters and variables with literal defaults get inferred types."""

    def test_function_params_inferred_from_defaults(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def f(x=0, y='hi', active=True, ratio=3.14, value=None): ...\n")
        from stubpy import generate_stub
        from stubpy.core.context import StubContext
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=StubContext())
        assert "x: int = 0" in stub
        assert "active: bool = True" in stub
        assert "ratio: float = 3.14" in stub
        assert "value = None" in stub

    def test_module_variable_types_inferred(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("MAX = 100\nLABEL = 'hi'\nFLAG = True\nRATE = 1.5\n")
        from stubpy import generate_stub
        from stubpy.core.context import StubContext
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=StubContext())
        assert "MAX: int" in stub
        assert "LABEL: str" in stub
        assert "FLAG: bool" in stub
        assert "RATE: float" in stub

    def test_list_type_inferred_homogeneous(self, tmp_path):
        """AST-only mode infers list[int] from homogeneous list literals.
        Runtime mode only gets the bare `list` (from type(value).__name__)."""
        src = tmp_path / "mod.py"
        src.write_text("ITEMS = [1, 2, 3]\nSTRS = ['a', 'b']\n")
        from stubpy import generate_stub
        from stubpy.config import ExecutionMode, StubConfig
        from stubpy.core.context import StubContext

        ctx_ast = StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY))
        stub_ast = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx_ast)
        assert "ITEMS: list[int]" in stub_ast
        assert "STRS: list[str]" in stub_ast

        ctx_rt = StubContext(config=StubConfig(execution_mode=ExecutionMode.RUNTIME))
        stub_rt = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx_rt)
        assert "ITEMS: list" in stub_rt

    def test_ast_only_same_quality_as_runtime_for_literals(self, tmp_path):
        """AST-only mode should give same annotations as runtime for literal defaults."""
        src = tmp_path / "mod.py"
        src.write_text("def f(x=42, y='hello', z=True, w=1.0): ...\n")
        from stubpy import generate_stub
        from stubpy.config import ExecutionMode, StubConfig
        from stubpy.core.context import StubContext
        stub_rt  = generate_stub(str(src), str(src.with_suffix(".pyi")),
                                 ctx=StubContext(config=StubConfig(execution_mode=ExecutionMode.RUNTIME)))
        stub_ast = generate_stub(str(src), str(src.with_suffix(".pyi")),
                                 ctx=StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY)))
        assert "x: int = 42" in stub_rt
        assert "x: int = 42" in stub_ast
        assert "z: bool = True" in stub_rt
        assert "z: bool = True" in stub_ast

    def test_explicit_annotation_wins_over_inferred(self, tmp_path):
        """When both annotation and default exist, explicit annotation wins."""
        src = tmp_path / "mod.py"
        src.write_text("def f(x: float = 0, y: str = 'hello') -> None: ...\n")
        from stubpy import generate_stub
        from stubpy.core.context import StubContext
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=StubContext())
        assert "x: float = 0" in stub
        assert "y: str = 'hello'" in stub
        assert "# type:" not in stub
