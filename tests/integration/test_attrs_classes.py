"""
``attrs`` classes: typed fields and the synthesised ``__init__``, from source and from a live class.
"""
from __future__ import annotations

import pytest

import stubpy
from stubpy import Config
from stubpy.emit import generate_class_stub
from stubpy.state.context import StubContext
from tests.conftest import write_tree

SOURCE = '''\
    import attr
    import attrs
    from attrs import define, frozen


    def to_int(value: str | int) -> int:
        return int(value)


    @attr.s
    class Legacy:
        plain = attr.ib()
        typed = attr.ib(type=int)
        count = attr.ib(default=3)
        items = attr.ib(factory=list)
        _secret = attr.ib(default="s")
        hidden = attr.ib(init=False, default=0)
        flag = attr.ib(kw_only=True, default=None)


    @attr.s(auto_attribs=True, kw_only=True)
    class Auto:
        a: int
        b: str = "x"


    @define
    class Modern:
        a: int
        b: list[int] = attrs.field(factory=list)
        c: int = attrs.field(converter=to_int, default=0)
        d: float = attrs.field(init=False)
        e: str = attrs.field(alias="name", default="")


    @frozen(kw_only=True)
    class Frozen:
        a: int


    @attr.dataclass
    class Data:
        a: int
        b: int = 2


    @define(init=False)
    class NoInit:
        a: int


    @define
    class Child(Modern):
        z: bool = False
'''


@pytest.fixture(params=["all", "none"])
def stub(request, tmp_path) -> str:
    root = write_tree(tmp_path, {"models.py": SOURCE})
    result = stubpy.render(root / "models.py", config=Config(imports=request.param))
    assert result.ok, result.diagnostics
    return result.text


def _section(text: str, start: str) -> str:
    return start + text.split(start, 1)[1].split("\nclass ", 1)[0]


def test_untyped_fields_take_type_keyword_default_or_factory(stub):
    legacy = _section(stub, "class Legacy:")
    for line in ("plain: Any", "typed: int", "count: int", "items: list", "flag: Any"):
        assert f"    {line}\n" in legacy
    assert "_secret" not in legacy


def test_legacy_init_strips_underscores_and_respects_init_and_kw_only(stub):
    legacy = _section(stub, "class Legacy:")
    init = legacy.split("def __init__(", 1)[1]
    assert "typed: int" in init and "count: int = 3" in init and "items: list = ..." in init
    assert "secret: str = 's'" in init or 'secret: str = "s"' in init
    assert "hidden" not in init
    assert init.index("*,") < init.index("flag")


def test_auto_attribs_and_kw_only_decorator(stub):
    auto = _section(stub, "class Auto:")
    assert "*," in auto and "a: int" in auto and ("b: str = 'x'" in auto or 'b: str = "x"' in auto)


def test_field_options_converter_alias_and_init_false(stub):
    init = _section(stub, "class Modern:").split("def __init__(", 1)[1]
    assert "b: list[int] = ..." in init
    assert "c: str | int = 0" in init
    assert "name: str" in init
    assert " d:" not in init


def test_frozen_dataclass_and_disabled_init(stub):
    assert "def __init__(self, *, a: int) -> None: ..." in _section(stub, "class Frozen:")
    assert "def __init__(self, a: int, b: int = 2) -> None: ..." in _section(stub, "class Data:")
    assert "__init__" not in _section(stub, "class NoInit:")


def test_subclass_init_lists_inherited_fields_first(stub):
    init = _section(stub, "class Child(Modern):").split("def __init__(", 1)[1]
    assert init.index("a: int") < init.index("z: bool = False")


def _live_attrs_class() -> type:
    namespace: dict = {}
    exec(compile("def __init__(self, a, b=None):\n    self.a = a\n", "<attrs generated init x>", "exec"), namespace)
    exec(compile("def __repr__(self):\n    return ''\n", "<attrs generated repr x>", "exec"), namespace)
    import enum

    class _Nothing(enum.Enum):
        NOTHING = 1

    init = namespace["__init__"]
    init.__defaults__ = (_Nothing.NOTHING,)
    init.__annotations__ = {"a": int, "b": list}
    field_a = type("Attribute", (), {"name": "a", "type": int})()
    field_b = type("Attribute", (), {"name": "b", "type": None})()
    return type("Live", (), {
        "__init__": init, "__repr__": namespace["__repr__"], "__attrs_attrs__": (field_a, field_b),
        "__module__": "elsewhere",
    })


def test_live_attrs_class_keeps_init_and_drops_generated_methods():
    text = generate_class_stub(_live_attrs_class(), StubContext())
    assert "    a: int\n" in text and "    b: Any\n" in text
    assert "def __init__(self, a: int, b: list = ...) -> None: ..." in text
    assert "__repr__" not in text and "_Nothing" not in text
