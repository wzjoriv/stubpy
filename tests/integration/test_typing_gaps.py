"""Typing details filled in by both modes: instance attributes, generators, ``NoReturn``, descriptors, slots, targets."""
from __future__ import annotations

import textwrap

import pytest

import stubpy
from stubpy import Config
from stubpy.cli import main

SOURCE = '''
    from typing import Any, overload

    class Handler:
        def __call__(self, x: int) -> int:
            return x

    handler = Handler()

    class Box:
        __slots__ = ("w", "h", "extra")

        def __init__(self, w: int, label: str = "") -> None:
            self.w = w
            self.h: float = 1.0
            self.label = label
            self.client = Handler()
            self.cache = None
            self._hidden = 1
            self.unknown = compute()

        def reset(self) -> None:
            self.cache = {}

    def compute():
        return 1

    def gen():
        yield 1
        yield 2

    def counter():
        received = yield 1
        return "done"

    async def agen():
        yield "a"

    def boom():
        raise ValueError("x")

    def todo():
        raise NotImplementedError

    class Base:
        @property
        def v(self) -> int:
            return 1

    class Sub(Base):
        @Base.v.setter
        def v(self, value: int) -> None: ...

    class Desc:
        @overload
        def __get__(self, obj: None, owner: Any) -> "Desc": ...
        @overload
        def __get__(self, obj: object, owner: Any) -> float: ...
        def __get__(self, obj, owner): ...

    class UsesDesc:
        d = Desc()

    @overload
    def f(x: int) -> int: ...
    @overload
    def f(x: int) -> int: ...
    @overload
    def f(x: str) -> str: ...
    def f(x):
        return x
'''


@pytest.fixture(scope="module")
def stub(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("typing") / "tg.py"
    path.write_text(textwrap.dedent(SOURCE), encoding="utf-8")
    return stubpy.render(str(path), config=Config()).text


def test_callable_instance_is_typed_by_its_class(stub):
    assert "handler: Handler" in stub


def test_instance_attributes(stub):
    body = stub.split("class Box:")[1].split("def __init__")[0]
    for line in ("w: int", "h: float", "label: str", "client: Handler", "cache: dict | None", "unknown: Any",
                 "extra: Any"):
        assert f"    {line}\n" in body, line
    assert "_hidden" not in body


def test_generators(stub):
    assert "def gen() -> Iterator[int]: ..." in stub
    assert "def counter() -> Generator[int, Any, str]: ..." in stub
    assert "def agen() -> AsyncIterator[str]: ..." in stub


def test_always_raising(stub):
    assert "def boom() -> NoReturn: ..." in stub
    assert "def todo(): ..." in stub


def test_inherited_getter_and_overridden_setter(stub):
    assert "class Sub(Base):\n    @property\n    def v(self) -> int: ...\n    @v.setter\n" in stub


def test_descriptor_attribute_type(stub):
    assert "class UsesDesc:\n    d: float" in stub


def test_overload_variants_deduplicated(stub):
    assert stub.count("def f(") == 2


@pytest.mark.parametrize(("target", "module"), [("3.10", "typing_extensions"), ("3.13", "typing")])
def test_target_python_picks_the_typing_module(tmp_path, target, module):
    path = tmp_path / "s.py"
    path.write_text("from typing import Self, override\n"
                    "class A:\n    @override\n    def m(self) -> Self: ...\n", encoding="utf-8")
    text = stubpy.render(str(path), config=Config(imports="none", target_python=target)).text
    assert f"from {module} import Self, override" in text


def test_target_python_validated():
    with pytest.raises(ValueError, match="target_python"):
        Config(target_python="three")
    assert Config.from_dict({"target-python": "3.12"}).target_version == (3, 12)


def test_target_python_cli_flag(tmp_path, capsys):
    path = tmp_path / "s.py"
    path.write_text("from typing import Self\nclass A:\n    def m(self) -> Self: ...\n", encoding="utf-8")
    assert main(["render", str(path), "--no-config", "--no-import", "--target-python", "3.11"]) == 0
    assert "from typing import Self" in capsys.readouterr().out
