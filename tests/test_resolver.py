"""
tests/test_resolver.py
-----------------------
Unit tests for stubpy.resolver.

Covers:
  - _detect_cls_call
  - _get_raw_params
  - resolve_params (flat, single-level, multi-level, *args, classmethod cls())
"""
from __future__ import annotations

import inspect

import pytest

from stubpy.resolver import (
    _KW_ONLY,
    _VAR_KW,
    _VAR_POS,
    _detect_cls_call,
    _get_raw_params,
    resolve_params,
)


# ---------------------------------------------------------------------------
# _detect_cls_call
# ---------------------------------------------------------------------------

class TestDetectClsCall:
    def test_regular_method_returns_false(self):
        class A:
            def __init__(self, **kwargs):
                pass
        detected, explicit = _detect_cls_call(A, "__init__")
        assert not detected

    def test_classmethod_without_cls_call(self):
        class A:
            @classmethod
            def make(cls, x: int):
                return x
        detected, explicit = _detect_cls_call(A, "make")
        assert not detected
        assert explicit == set()

    def test_cls_call_bare_kwargs(self):
        class Widget:
            @classmethod
            def create(cls, **kwargs):
                return cls(**kwargs)
        detected, explicit = _detect_cls_call(Widget, "create")
        assert detected
        assert explicit == set()

    def test_cls_call_with_explicit_keyword(self):
        class Widget:
            @classmethod
            def colored(cls, color: str, **kwargs):
                return cls(color=color, **kwargs)
        detected, explicit = _detect_cls_call(Widget, "colored")
        assert detected
        assert "color" in explicit

    def test_cls_call_multiple_explicit(self):
        class C:
            @classmethod
            def unit(cls, **kwargs):
                return cls(r=1, cx=0, cy=0, **kwargs)
        detected, explicit = _detect_cls_call(C, "unit")
        assert detected
        assert explicit == {"r", "cx", "cy"}

    def test_method_not_in_dict(self):
        class A:
            pass
        detected, explicit = _detect_cls_call(A, "nonexistent")
        assert not detected
        assert explicit == set()


# ---------------------------------------------------------------------------
# _get_raw_params
# ---------------------------------------------------------------------------

class TestGetRawParams:
    def test_method_not_defined_on_class(self):
        class A:
            pass
        params, hints = _get_raw_params(A, "__init__")
        assert params is None
        assert hints == {}

    def test_simple_init(self):
        class A:
            def __init__(self, x: int, y: str = "hi"):
                pass
        params, hints = _get_raw_params(A, "__init__")
        assert params is not None
        assert [p.name for p in params] == ["x", "y"]
        assert hints.get("x") is int
        assert hints.get("y") is str

    def test_excludes_self(self):
        class A:
            def __init__(self, x: int):
                pass
        params, _ = _get_raw_params(A, "__init__")
        assert all(p.name != "self" for p in params)

    def test_excludes_cls(self):
        class A:
            @classmethod
            def make(cls, v: int):
                return cls()
        params, _ = _get_raw_params(A, "make")
        assert all(p.name != "cls" for p in params)

    def test_static_method(self):
        class A:
            @staticmethod
            def add(a: int, b: int) -> int:
                return a + b
        params, hints = _get_raw_params(A, "add")
        assert params is not None
        assert [p.name for p in params] == ["a", "b"]


# ---------------------------------------------------------------------------
# resolve_params — no variadics (pass-through)
# ---------------------------------------------------------------------------

class TestResolveParamsFlat:
    def test_plain_params_unchanged(self):
        class A:
            def __init__(self, x: int, y: str):
                pass
        result = resolve_params(A, "__init__")
        assert [p.name for p, _ in result] == ["x", "y"]

    def test_open_kwargs_preserved_when_no_parent(self):
        class W:
            def __init__(self, x: str, **kwargs):
                pass
        result = resolve_params(W, "__init__")
        kinds = [p.kind for p, _ in result]
        assert _VAR_KW in kinds

    def test_not_defined_on_class_delegates_to_ancestor(self):
        class Parent:
            def helper(self, n: int) -> None:
                pass
        class Child(Parent):
            pass
        result = resolve_params(Child, "helper")
        assert len(result) == 1
        assert result[0][0].name == "n"


# ---------------------------------------------------------------------------
# resolve_params — single-level **kwargs
# ---------------------------------------------------------------------------

class TestResolveParamsSingleKwargs:
    def setup_method(self):
        class Parent:
            def __init__(self, color: str, size: int = 10):
                pass
        class Child(Parent):
            def __init__(self, label: str, **kwargs):
                super().__init__(**kwargs)
        self.Parent = Parent
        self.Child = Child

    def test_own_params_present(self):
        result = resolve_params(self.Child, "__init__")
        names = [p.name for p, _ in result]
        assert "label" in names

    def test_parent_params_merged(self):
        result = resolve_params(self.Child, "__init__")
        names = [p.name for p, _ in result]
        assert "color" in names
        assert "size" in names

    def test_kwargs_removed(self):
        result = resolve_params(self.Child, "__init__")
        assert _VAR_KW not in [p.kind for p, _ in result]

    def test_own_param_comes_first(self):
        result = resolve_params(self.Child, "__init__")
        names = [p.name for p, _ in result]
        assert names.index("label") < names.index("color")

    def test_defaults_preserved(self):
        result = resolve_params(self.Child, "__init__")
        size_param = next(p for p, _ in result if p.name == "size")
        assert size_param.default == 10


# ---------------------------------------------------------------------------
# resolve_params — multi-level **kwargs
# ---------------------------------------------------------------------------

class TestResolveParamsMultiLevel:
    def setup_method(self):
        class A:
            def __init__(self, name: str, legs: int, wild: bool = True):
                pass
        class B(A):
            def __init__(self, owner: str, **kwargs):
                super().__init__(**kwargs)
        class C(B):
            def __init__(self, breed: str, **kwargs):
                super().__init__(**kwargs)
        class D(C):
            def __init__(self, job: str, **kwargs):
                super().__init__(**kwargs)
        self.A, self.B, self.C, self.D = A, B, C, D

    def test_three_levels_all_params(self):
        result = resolve_params(self.C, "__init__")
        names = [p.name for p, _ in result]
        for expected in ("breed", "owner", "name", "legs"):
            assert expected in names

    def test_three_levels_no_kwargs(self):
        result = resolve_params(self.C, "__init__")
        assert _VAR_KW not in [p.kind for p, _ in result]

    def test_four_levels_all_params(self):
        result = resolve_params(self.D, "__init__")
        names = [p.name for p, _ in result]
        for expected in ("job", "breed", "owner", "name", "wild"):
            assert expected in names

    def test_own_param_ordering_respected(self):
        result = resolve_params(self.C, "__init__")
        names = [p.name for p, _ in result]
        assert names.index("breed") < names.index("owner") < names.index("name")

    def test_boolean_default_preserved(self):
        result = resolve_params(self.D, "__init__")
        wild_param = next(p for p, _ in result if p.name == "wild")
        assert wild_param.default is True


# ---------------------------------------------------------------------------
# resolve_params — *args (VAR_POS)
# ---------------------------------------------------------------------------

class TestResolveParamsVarPos:
    def test_explicitly_typed_args_preserved(self):
        class A:
            def __init__(self, *items: str):
                pass
        result = resolve_params(A, "__init__")
        kinds = [p.kind for p, _ in result]
        assert _VAR_POS in kinds

    def test_unresolved_untyped_args_preserved(self):
        """*args that can't be resolved to a parent is kept."""
        class A:
            def __init__(self, *args):
                pass
        result = resolve_params(A, "__init__")
        kinds = [p.kind for p, _ in result]
        assert _VAR_POS in kinds

    def test_typed_star_args_with_kw_and_kwargs(self):
        class Parent:
            def __init__(self, id: str = None):
                pass
        class Child(Parent):
            def __init__(self, *items: str, label: str = "", **kwargs):
                super().__init__(**kwargs)
        result = resolve_params(Child, "__init__")
        names = [p.name for p, _ in result]
        # *items (typed) must survive
        assert "items" in names
        assert "label" in names
        assert "id" in names

    def test_star_args_position_before_kw_only(self):
        class Parent:
            def __init__(self, id: str = None):
                pass
        class Child(Parent):
            def __init__(self, *items: str, label: str = "", **kwargs):
                super().__init__(**kwargs)
        result = resolve_params(Child, "__init__")
        names = [p.name for p, _ in result]
        assert names.index("items") < names.index("label")


# ---------------------------------------------------------------------------
# resolve_params — @classmethod cls() backtracing
# ---------------------------------------------------------------------------

class TestResolveParamsClassmethod:
    def test_simple_cls_call_gets_init_params(self):
        class Widget:
            def __init__(self, width: int, height: int, color: str = "black"):
                pass
            @classmethod
            def square(cls, **kwargs):
                return cls(**kwargs)
        result = resolve_params(Widget, "square")
        names = [p.name for p, _ in result]
        assert "width" in names
        assert "height" in names
        assert "color" in names
        assert _VAR_KW not in [p.kind for p, _ in result]

    def test_explicit_param_excluded_from_init_merge(self):
        class Widget:
            def __init__(self, width: int, height: int, color: str = "black"):
                pass
            @classmethod
            def colored(cls, color: str, **kwargs):
                return cls(color=color, **kwargs)
        result = resolve_params(Widget, "colored")
        names = [p.name for p, _ in result]
        # color appears exactly once (as own param of colored)
        assert names.count("color") == 1
        assert names[0] == "color"  # own param first

    def test_chained_cls_call_through_init_chain(self):
        class Base:
            def __init__(self, x: int, y: int):
                pass
        class Child(Base):
            def __init__(self, label: str, **kwargs):
                super().__init__(**kwargs)
            @classmethod
            def make(cls, **kwargs):
                return cls(**kwargs)
        result = resolve_params(Child, "make")
        names = [p.name for p, _ in result]
        assert "label" in names
        assert "x" in names
        assert "y" in names
        assert _VAR_KW not in [p.kind for p, _ in result]

    def test_multiple_hardcoded_args_excluded(self):
        class Shape:
            def __init__(self, cx: float, cy: float, r: float, color: str = "black"):
                pass
            @classmethod
            def unit(cls, **kwargs):
                return cls(cx=0, cy=0, r=1, **kwargs)
        result = resolve_params(Shape, "unit")
        names = [p.name for p, _ in result]
        # cx, cy, r are hardcoded → not in stub
        assert "cx" not in names
        assert "cy" not in names
        assert "r" not in names
        # color is not hardcoded → present
        assert "color" in names


# ---------------------------------------------------------------------------
# resolve_params — keyword-only params
# ---------------------------------------------------------------------------

class TestResolveParamsKwOnly:
    def test_kw_only_kind_preserved(self):
        class A:
            def __init__(self, x: int, *, y: str = "x"):
                pass
        result = resolve_params(A, "__init__")
        y_param = next(p for p, _ in result if p.name == "y")
        assert y_param.kind == _KW_ONLY

    def test_kw_only_from_parent_retained(self):
        class Parent:
            def __init__(self, *, label: str = ""):
                pass
        class Child(Parent):
            def __init__(self, name: str, **kwargs):
                super().__init__(**kwargs)
        result = resolve_params(Child, "__init__")
        label_param = next(p for p, _ in result if p.name == "label")
        assert label_param.kind == _KW_ONLY


# ---------------------------------------------------------------------------
# resolve_params — positional-only parameter handling
# ---------------------------------------------------------------------------

class TestResolveParamsPosOnly:
    """Positional-only parameters are handled correctly in MRO backtracing."""

    def test_pos_only_params_preserved_own_method(self):
        """Own positional-only params keep POSITIONAL_ONLY kind."""
        class A:
            def method(self, x: int, y: int, /) -> None:
                pass

        result = resolve_params(A, "method")
        kinds = {p.name: p.kind for p, _ in result}
        assert kinds["x"] == inspect.Parameter.POSITIONAL_ONLY
        assert kinds["y"] == inspect.Parameter.POSITIONAL_ONLY

    def test_pos_only_absorbed_by_kwargs_promoted(self):
        """Parent's pos-only params absorbed by child **kwargs become POSITIONAL_OR_KEYWORD."""
        class Parent:
            def __init__(self, x: int, y: int, /) -> None:
                pass

        class Child(Parent):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)

        result = resolve_params(Child, "__init__")
        kinds = {p.name: p.kind for p, _ in result}
        # x and y are pos-only in Parent but become POS_OR_KW in Child's kwargs
        assert kinds.get("x") == inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert kinds.get("y") == inspect.Parameter.POSITIONAL_OR_KEYWORD

    def test_pos_only_not_duplicated_in_merge(self):
        """A pos-only param already named in the child is not duplicated."""
        class Parent:
            def __init__(self, x: int, /) -> None:
                pass

        class Child(Parent):
            def __init__(self, x: int, **kwargs) -> None:
                super().__init__(x, **kwargs)

        result = resolve_params(Child, "__init__")
        names = [p.name for p, _ in result]
        assert names.count("x") == 1

    def test_mixed_pos_only_and_regular_order(self):
        """Pos-only params precede regular params after MRO merge."""
        class Parent:
            def __init__(self, a: int, b: str, /) -> None:
                pass

        class Child(Parent):
            def __init__(self, c: float, **kwargs) -> None:
                super().__init__(**kwargs)

        result = resolve_params(Child, "__init__")
        names = [p.name for p, _ in result]
        assert "c" in names
        # a and b (from parent) should also appear
        assert "a" in names
        assert "b" in names
