"""Types a binding does not state come from a hand-written ``.pyi`` beside the extension module, when there is one."""
from __future__ import annotations

from stubpy.compiled.introspect._hand_stub import sibling_annotations

from .fakes import FakeBuiltin, fake_module
from .test_introspect import _render

HAND = '''\
class Holder:
    @property
    def tag(self) -> str: ...
    count: int
    def grow(self, n: int) -> "Holder": ...

def area(points, /) -> float: ...
def opaque() -> list[int]: ...
def secret() -> Mystery: ...
'''


class Holder:
    __slots__ = ("tag", "count")
    grow = FakeBuiltin("grow", "grow(self, n)")


Holder.__module__ = "fakeext"


def _module(tmp_path):
    (tmp_path / "fakeext.pyi").write_text(HAND, encoding="utf-8")
    module = fake_module(Holder=Holder, secret=FakeBuiltin("secret", "secret()"))
    module.__file__ = str(tmp_path / "fakeext.cp311-win_amd64.pyd")
    return module


def test_sibling_annotations(tmp_path):
    found = sibling_annotations(_module(tmp_path))
    assert found["Holder.tag"] == "str" and found["Holder.count"] == "int" and found["area"] == "float"


def test_getset_and_member_types_come_from_the_stub(tmp_path):
    text, _ = _render(_module(tmp_path))
    holder = text.split("class Holder")[1].split("\nclass ")[0]
    assert "def tag(self) -> str: ..." in holder and "def count(self) -> int: ..." in holder


def test_missing_returns_come_from_the_stub(tmp_path):
    text, _ = _render(_module(tmp_path))
    assert "def area(points, /) -> float: ..." in text
    assert "def grow(self, n) -> Holder: ..." in text
    assert "def opaque(*args: Any, **kwargs: Any) -> list[int]: ..." in text


def test_names_the_stub_cannot_bind_are_not_used(tmp_path):
    text, _ = _render(_module(tmp_path))
    assert "def secret() -> Mystery" not in text and "def secret()" in text


def test_no_file_means_no_annotations():
    assert sibling_annotations(fake_module()) == {}
