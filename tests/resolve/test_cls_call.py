"""Tests for cls(..., **kwargs) detection."""
from __future__ import annotations

from stubpy.resolve._cls_call import detect_cls_call


class TestDetectClsCall:
    def test_regular_method_returns_false(self):
        class A:
            def __init__(self, **kwargs):
                pass
        detected, explicit = detect_cls_call(A, "__init__")
        assert not detected

    def test_classmethod_without_cls_call(self):
        class A:
            @classmethod
            def make(cls, x: int):
                return x
        detected, explicit = detect_cls_call(A, "make")
        assert not detected
        assert explicit == set()

    def test_cls_call_bare_kwargs(self):
        class Widget:
            @classmethod
            def create(cls, **kwargs):
                return cls(**kwargs)
        detected, explicit = detect_cls_call(Widget, "create")
        assert detected
        assert explicit == set()

    def test_cls_call_with_explicit_keyword(self):
        class Widget:
            @classmethod
            def colored(cls, color: str, **kwargs):
                return cls(color=color, **kwargs)
        detected, explicit = detect_cls_call(Widget, "colored")
        assert detected
        assert "color" in explicit

    def test_cls_call_multiple_explicit(self):
        class C:
            @classmethod
            def unit(cls, **kwargs):
                return cls(r=1, cx=0, cy=0, **kwargs)
        detected, explicit = detect_cls_call(C, "unit")
        assert detected
        assert explicit == {"r", "cx", "cy"}

    def test_method_not_in_dict(self):
        class A:
            pass
        detected, explicit = detect_cls_call(A, "nonexistent")
        assert not detected
        assert explicit == set()
