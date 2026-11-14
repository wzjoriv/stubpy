"""Tests for resolve_params: MRO backtracing of methods."""
from __future__ import annotations

import inspect

from stubpy._constants import KW_ONLY, VAR_KW, VAR_POS
from stubpy.resolve import resolve_params


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
        assert VAR_KW in kinds

    def test_not_defined_on_class_delegates_to_ancestor(self):
        class Parent:
            def helper(self, n: int) -> None:
                pass
        class Child(Parent):
            pass
        result = resolve_params(Child, "helper")
        assert len(result) == 1
        assert result[0][0].name == "n"


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
        assert VAR_KW not in [p.kind for p, _ in result]

    def test_own_param_comes_first(self):
        result = resolve_params(self.Child, "__init__")
        names = [p.name for p, _ in result]
        assert names.index("label") < names.index("color")

    def test_defaults_preserved(self):
        result = resolve_params(self.Child, "__init__")
        size_param = next(p for p, _ in result if p.name == "size")
        assert size_param.default == 10


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
        assert VAR_KW not in [p.kind for p, _ in result]

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


class TestResolveParamsVarPos:
    def test_explicitly_typed_args_preserved(self):
        class A:
            def __init__(self, *items: str):
                pass
        result = resolve_params(A, "__init__")
        kinds = [p.kind for p, _ in result]
        assert VAR_POS in kinds

    def test_unresolved_untyped_args_preserved(self):
        """*args that can't be resolved to a parent is kept."""
        class A:
            def __init__(self, *args):
                pass
        result = resolve_params(A, "__init__")
        kinds = [p.kind for p, _ in result]
        assert VAR_POS in kinds

    def test_typed_star_args_with_kw_and_kwargs(self):
        class Parent:
            def __init__(self, id: str = None):
                pass
        class Child(Parent):
            def __init__(self, *items: str, label: str = "", **kwargs):
                super().__init__(**kwargs)
        result = resolve_params(Child, "__init__")
        names = [p.name for p, _ in result]
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
        assert VAR_KW not in [p.kind for p, _ in result]

    def test_explicit_param_excluded_from_init_merge(self):
        class Widget:
            def __init__(self, width: int, height: int, color: str = "black"):
                pass
            @classmethod
            def colored(cls, color: str, **kwargs):
                return cls(color=color, **kwargs)
        result = resolve_params(Widget, "colored")
        names = [p.name for p, _ in result]
        assert names.count("color") == 1
        assert names[0] == "color"

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
        assert VAR_KW not in [p.kind for p, _ in result]

    def test_multiple_hardcoded_args_excluded(self):
        class Shape:
            def __init__(self, cx: float, cy: float, r: float, color: str = "black"):
                pass
            @classmethod
            def unit(cls, **kwargs):
                return cls(cx=0, cy=0, r=1, **kwargs)
        result = resolve_params(Shape, "unit")
        names = [p.name for p, _ in result]
        assert "cx" not in names
        assert "cy" not in names
        assert "r" not in names
        assert "color" in names


class TestResolveParamsKwOnly:
    def test_kw_only_kind_preserved(self):
        class A:
            def __init__(self, x: int, *, y: str = "x"):
                pass
        result = resolve_params(A, "__init__")
        y_param = next(p for p, _ in result if p.name == "y")
        assert y_param.kind == KW_ONLY

    def test_kw_only_from_parent_retained(self):
        class Parent:
            def __init__(self, *, label: str = ""):
                pass
        class Child(Parent):
            def __init__(self, name: str, **kwargs):
                super().__init__(**kwargs)
        result = resolve_params(Child, "__init__")
        label_param = next(p for p, _ in result if p.name == "label")
        assert label_param.kind == KW_ONLY


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

    def test_pos_only_not_reachable_through_kwargs(self):
        """Parent's pos-only params cannot be filled through child **kwargs, so they are dropped."""
        class Parent:
            def __init__(self, x: int, y: int, /) -> None:
                pass

        class Child(Parent):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)

        result = resolve_params(Child, "__init__")
        names = [p.name for p, _ in result]
        assert "x" not in names
        assert "y" not in names

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
        """Pos-only params forwarded through *args precede the child's keyword-only params."""
        class Parent:
            def __init__(self, a: int, b: str, /) -> None:
                pass

        class Child(Parent):
            def __init__(self, c: float, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)

        result = resolve_params(Child, "__init__")
        names = [p.name for p, _ in result]
        assert "c" in names
        assert "a" in names
        assert "b" in names
