"""Tests for stubpy.resolve.hints."""
from __future__ import annotations

from stubpy.resolve.hints import get_raw_params


def _own(src: str, name: str) -> dict:
    from stubpy.resolve.hints import get_own_annotations

    ns: dict = {}
    exec(compile(src, "<test>", "exec", dont_inherit=True), ns)
    return get_own_annotations(ns[name])


class TestGetRawParams:
    def test_method_not_defined_on_class(self):
        class A:
            pass
        params, hints = get_raw_params(A, "__init__")
        assert params is None
        assert hints == {}

    def test_simple_init(self):
        class A:
            def __init__(self, x: int, y: str = "hi"):
                pass
        params, hints = get_raw_params(A, "__init__")
        assert params is not None
        assert [p.name for p in params] == ["x", "y"]
        assert hints.get("x") is int
        assert hints.get("y") is str

    def test_excludes_self(self):
        class A:
            def __init__(self, x: int):
                pass
        params, _ = get_raw_params(A, "__init__")
        assert all(p.name != "self" for p in params)

    def test_excludes_cls(self):
        class A:
            @classmethod
            def make(cls, v: int):
                return cls()
        params, _ = get_raw_params(A, "make")
        assert all(p.name != "cls" for p in params)

    def test_static_method(self):
        class A:
            @staticmethod
            def add(a: int, b: int) -> int:
                return a + b
        params, hints = get_raw_params(A, "add")
        assert params is not None
        assert [p.name for p in params] == ["a", "b"]


class TestGetOwnAnnotations:
    def test_class_annotations(self):
        assert _own("class Foo:\n    x: int\n    y: str = 'a'\n", "Foo") == {"x": int, "y": str}

    def test_inherited_annotations_excluded(self):
        src = "class Base:\n    x: int\nclass Child(Base):\n    y: str\n"
        assert _own(src, "Child") == {"y": str}

    def test_class_without_own_annotations_ignores_parent(self):
        src = "class Base:\n    x: int\nclass Child(Base):\n    pass\n"
        assert _own(src, "Child") == {}

    def test_no_annotations(self):
        assert _own("class Empty:\n    pass\n", "Empty") == {}

    def test_undefined_forward_ref_does_not_raise(self):
        ann = _own("class Foo:\n    x: 'Missing'\n    y: int\n", "Foo")
        assert set(ann) == {"x", "y"}
        assert ann["y"] is int

    def test_future_annotations_stay_strings(self):
        src = "from __future__ import annotations\nclass Foo:\n    x: int\n"
        assert _own(src, "Foo") == {"x": "int"}

    def test_function_annotations(self):
        assert _own("def f(a: int) -> str: ...\n", "f") == {"a": int, "return": str}

    def test_non_annotatable_object(self):
        from stubpy.resolve.hints import get_own_annotations

        assert get_own_annotations(42) == {}
