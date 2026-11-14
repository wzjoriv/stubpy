"""Tests for class stubs."""
from __future__ import annotations

import ast

import pytest

import stubpy
from stubpy.emit import generate_class_stub
from tests.conftest import (
    assert_valid_syntax,
    flatten,
    make_stub,
)


class TestGenerateClassStub:
    def test_class_line(self, ctx):
        class MyClass: pass
        stub = generate_class_stub(MyClass, ctx)
        assert stub.startswith("class MyClass:")

    def test_base_class_in_signature(self, ctx):
        class Parent: pass
        class Child(Parent): pass
        stub = generate_class_stub(Child, ctx)
        assert "class Child(Parent):" in stub

    def test_multiple_bases(self, ctx):
        class A: pass
        class B: pass
        class C(A, B): pass
        stub = generate_class_stub(C, ctx)
        assert "class C(A, B):" in stub

    def test_object_base_omitted(self, ctx):
        class A: pass
        stub = generate_class_stub(A, ctx)
        assert "object" not in stub

    def test_empty_class_gets_ellipsis(self, ctx):
        class Empty: pass
        stub = generate_class_stub(Empty, ctx)
        assert "    ..." in stub

    def test_class_level_annotations(self, ctx):
        class A:
            x: int
            y: str
        stub = generate_class_stub(A, ctx)
        assert "    x: int" in stub
        assert "    y: str" in stub

    def test_methods_indented(self, ctx):
        class A:
            def foo(self) -> None: pass
        stub = generate_class_stub(A, ctx)
        assert "    def foo(self) -> None: ..." in stub

    def test_valid_python_syntax(self, ctx):
        class A:
            def __init__(self, x: int, y: str, z: float = 1.0) -> None: pass
            def method(self) -> None: pass
        stub = generate_class_stub(A, ctx)
        try:
            ast.parse(stub)
        except SyntaxError as exc:
            pytest.fail(f"Invalid syntax in class stub: {exc}")


class TestSpecialClassIntegration:

    def test_all_patterns_combined(self):
        c = make_stub(
            "import abc\n"
            "from dataclasses import dataclass\n"
            "from typing import NamedTuple\n"
            "\n"
            "class Color(NamedTuple):\n"
            "    r: int\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
            "\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float = 0.0\n"
            "\n"
            "class Renderer(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def render(self, ctx: dict) -> str: ...\n"
        )
        assert_valid_syntax(c)
        assert "class Color(NamedTuple):" in c
        assert "@dataclass" in c
        assert "class Point:" in c
        assert "class Renderer(ABC):" in c
        assert "@abstractmethod" in c
        assert "async def render" in c

    def test_dataclass_with_abc_base(self):
        c = make_stub(
            "import abc\n"
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Entity(abc.ABC):\n"
            "    id: int\n"
            "    @abc.abstractmethod\n"
            "    def serialize(self) -> dict: ...\n"
        )
        assert_valid_syntax(c)
        assert "@dataclass" in c
        assert "class Entity(ABC):" in c
        assert "@abstractmethod" in c
        assert "def __init__" in c

    def test_kwargs_backtracing_unaffected(self):
        c = make_stub(
            "class Base:\n"
            "    def __init__(self, x: float, y: float = 0.0) -> None: pass\n"
            "class Child(Base):\n"
            "    def __init__(self, label: str, **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        child_section = c.split("class Child")[1]
        init_line = [l for l in flatten(child_section).splitlines()
                     if "def __init__" in l][0]
        assert "label: str" in init_line
        assert "x: float" in init_line
        assert "**kwargs" not in init_line

    def test_async_in_abc(self):
        c = make_stub(
            "import abc\n"
            "class Stream(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def read(self, n: int) -> bytes: ...\n"
            "    async def write(self, data: bytes) -> None: pass\n"
        )
        assert_valid_syntax(c)
        assert "@abstractmethod" in c
        assert c.count("async def") == 2

    def test_full_combination_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "import abc\n"
            "from dataclasses import dataclass, field\n"
            "from typing import NamedTuple, Optional\n"
            "\n"
            "class RGB(NamedTuple):\n"
            "    r: int = 0\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
            "\n"
            "@dataclass\n"
            "class Config:\n"
            "    host: str\n"
            "    port: int = 8080\n"
            "    tags: list = field(default_factory=list)\n"
            "\n"
            "class Protocol(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def connect(self, cfg: Config) -> None: ...\n"
            "    @abc.abstractmethod\n"
            "    async def send(self, data: bytes) -> int: ...\n"
            "    def close(self) -> None: pass\n"
        ))

    def test_graphics_demo_backward_compat(self):
        from pathlib import Path

        demo = Path(__file__).parents[2] / "demo" / "graphics.py"
        c = stubpy.render(str(demo)).text
        assert_valid_syntax(c)
        for cls_name in ("Shape", "Path", "Arc", "Rectangle", "Square", "Circle"):
            assert f"class {cls_name}" in c
        arc_section = c.split("class Arc")[1].split("\nclass ")[0]
        assert "angle: float" in arc_section
        assert "**kwargs" not in arc_section
