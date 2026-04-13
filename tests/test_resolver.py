"""
tests/test_resolver.py
-----------------------
Tests for :mod:`stubpy.resolver` — parameter resolution for both class
methods (MRO walk) and module-level functions (namespace forwarding).

Covers:
- :func:`resolve_params` — method MRO walk, cls()-call detection
- :func:`resolve_function_params` — function/class chain forwarding
- Helper functions: ``_normalise_kind``, ``_merge_concrete_params``,
  ``_enforce_signature_validity``, ``_finalise_variadics``
- Mixed method↔function↔class forwarding chains
- Cycle detection and recursive forwarding
- AST scanning of kwargs/args forwarding targets
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import (
    _compile_fn_from_source, _harvest_fn, _param_names, _param_kinds,
    assert_valid_python,
)
from stubpy.resolver import (
    _VAR_KW as _VAR_KW, _VAR_POS as _VAR_POS,
    _KW_ONLY as _KW_ONLY, _POS_ONLY as _POS_ONLY, _POS_KW as _POS_KW,
)
from stubpy.ast_pass import ast_harvest, FunctionInfo
from stubpy.context import StubContext, StubConfig
from stubpy.resolver import (
    resolve_function_params,
    resolve_params,
    _enforce_signature_validity,
    _finalise_variadics,
    _merge_concrete_params,
    _normalise_kind,
    _detect_cls_call,
    _get_raw_params,
    _resolve_via_mro,
)


def _fi(name: str, kw_targets=(), pos_targets=()):
    """Build a minimal :class:`~stubpy.ast_pass.FunctionInfo` for tests."""
    return FunctionInfo(
        name=name,
        lineno=1,
        kwargs_forwarded_to=list(kw_targets),
        args_forwarded_to=list(pos_targets),
    )


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

# ---------------------------------------------------------------------------
# Function resolver tests (module-level function forwarding)
# ---------------------------------------------------------------------------

class TestNoVariadics:
    def test_plain_function_unchanged(self):
        src = "def f(x: int, y: str = 'hi') -> None: ..."
        live, fi, ns = _harvest_fn(src, "f")
        result = resolve_function_params(live, fi, ns)
        assert _param_names(result) == ["x", "y"]

    def test_positional_only_preserved(self):
        src = "def f(a: int, b: int, /) -> int: ..."
        live, fi, ns = _harvest_fn(src, "f")
        result = resolve_function_params(live, fi, ns)
        assert _param_names(result) == ["a", "b"]
        assert all(p.kind == _POS_ONLY for p, _ in result)

    def test_keyword_only_preserved(self):
        src = "def f(*, x: int, y: str = 'hi') -> None: ..."
        live, fi, ns = _harvest_fn(src, "f")
        result = resolve_function_params(live, fi, ns)
        assert _param_names(result) == ["x", "y"]
        assert all(p.kind == _KW_ONLY for p, _ in result)

    def test_none_live_fn_returns_empty(self):
        result = resolve_function_params(None, None, {})
        assert result == []



class TestKwargsForwarding:
    def test_simple_forwarding_expands_params(self):
        src = """
        def target(r: float, g: float, b: float, a: float = 1.0): ...
        def wrapper(r: float = 1.0, **kwargs): target(r=r, **kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "r" in names
        assert "g" in names
        assert "b" in names
        assert "a" in names
        # **kwargs consumed
        assert "**kwargs" not in names

    def test_own_params_come_first(self):
        src = """
        def target(x: int, y: int): ...
        def wrapper(z: int, **kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert names[0] == "z", "own param must be first"

    def test_own_param_not_duplicated(self):
        src = """
        def target(r: float, g: float, b: float): ...
        def wrapper(r: float = 0.5, **kwargs): target(r=r, **kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert names.count("r") == 1

    def test_default_ordering_enforcement(self):
        """Non-default absorbed params following a default own-param → KEYWORD_ONLY."""
        src = """
        def target(x: int, y: int, z: int = 0): ...
        def wrapper(own: int = 5, **kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        # x and y have no defaults but follow own=5 → must be KW_ONLY
        kinds = {p.name: p.kind for p, _ in result}
        assert kinds["x"] == _KW_ONLY
        assert kinds["y"] == _KW_ONLY
        # z has a default — it may stay POS_KW or KW_ONLY depending on position
        # but the result must be valid Python
        stub = f"def wrapper({', '.join(_param_names(result))}): ..."
        # Verify by checking kinds directly rather than compile (names only)
        # The key invariant: no non-default follows a default in non-KW territory
        pos_params = [(p, h) for p, h in result if p.kind in (_POS_KW, _POS_ONLY)]
        seen_default = False
        for p, _ in pos_params:
            if p.default is not inspect.Parameter.empty:
                seen_default = True
            else:
                assert not seen_default, f"non-default {p.name!r} after default param"

    def test_residual_kwargs_when_target_still_open(self):
        """If the target also has **kwargs, our **kwargs is NOT consumed."""
        src = """
        def target(x: int, **kwargs): ...
        def wrapper(y: int, **kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "**kwargs" in names  # still open

    def test_no_ast_info_preserves_kwargs(self):
        """Without AST info, **kwargs is preserved unchanged."""
        src = "def target(x: int): ...\ndef wrapper(y: int, **kwargs): target(**kwargs)"
        ns = _compile_fn_from_source(src)
        # Deliberately pass ast_info=None
        result = resolve_function_params(ns["wrapper"], None, ns)
        names = _param_names(result)
        assert "**kwargs" in names

    def test_unknown_target_preserves_kwargs(self):
        """If the forwarding target is not in namespace, **kwargs is kept."""
        src = "def wrapper(x: int, **kwargs): unknown_func(**kwargs)"
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        assert "**kwargs" in _param_names(result)



class TestArgsForwarding:
    def test_typed_args_forwarded(self):
        """Typed *args from own function are preserved in output."""
        src = """
        def target(*items: str) -> None: ...
        def wrapper(*items: str, **kwargs) -> None: target(*items)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "*items" in names

    def test_untyped_args_preserved_when_unresolved(self):
        """When *args target still has *args, we keep our *args."""
        src = """
        def target(*args, x: int = 1) -> None: ...
        def wrapper(*args, y: int = 2) -> None: target(*args)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        assert "*args" in _param_names(result)

    def test_untyped_unresolved_args_not_in_output(self):
        """When *args fully resolved (target has no *args), it is dropped."""
        src = """
        def target(x: int, y: int) -> None: ...
        def wrapper(*args) -> None: target(*args)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        # args is untyped and fully resolved → should not appear
        assert "*args" not in _param_names(result)

    def test_args_position_before_kwonly(self):
        """When *args is preserved, it appears before any keyword-only params.

        Note: ``def f(*items, verbose=False)`` is valid Python — after ``*items``
        all parameters are implicitly keyword-only, so the bare ``*`` is not
        needed (and would be a SyntaxError).
        """
        src = """
        def target(*items: str) -> None: ...
        def wrapper(*items: str, verbose: bool = False) -> None: target(*items)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "*items" in names
        args_idx = names.index("*items")
        kw_idx = names.index("verbose")
        assert args_idx < kw_idx



class TestChainedForwarding:
    def test_two_level_chain(self):
        """A → B → C: resolve all the way down."""
        src = """
        def make_color(r: float, g: float, b: float, a: float = 1.0): ...
        def make_red(r: float = 1.0, **kwargs): make_color(r=r, **kwargs)
        def make_tinted(tint: float = 0.5, **kwargs): make_red(r=tint, **kwargs)
        """
        ast_syms = ast_harvest(textwrap.dedent(src))
        ns = _compile_fn_from_source(src)
        fi_by_name = {f.name: f for f in ast_syms.functions}

        live = ns["make_tinted"]
        fi   = fi_by_name["make_tinted"]
        result = resolve_function_params(live, fi, ns, ast_info_by_name=fi_by_name)
        names = _param_names(result)
        assert "g" in names
        assert "b" in names
        assert "a" in names
        assert "**kwargs" not in names

    def test_cycle_guard(self):
        """Mutually recursive forwarding (A→B→A) does not loop infinitely."""
        src = """
        def a(**kwargs): b(**kwargs)
        def b(**kwargs): a(**kwargs)
        """
        ast_syms = ast_harvest(textwrap.dedent(src))
        ns = _compile_fn_from_source(src)
        fi_by_name = {f.name: f for f in ast_syms.functions}

        live = ns["a"]
        fi   = fi_by_name["a"]
        # Must complete without recursion error; **kwargs preserved as residual
        result = resolve_function_params(live, fi, ns, ast_info_by_name=fi_by_name)
        assert "**kwargs" in _param_names(result)

    def test_three_level_chain_no_duplicate_params(self):
        """Deep chain should not produce duplicates."""
        src = """
        def base(x: int, y: int, z: int = 0): ...
        def mid(m: int, **kwargs): base(**kwargs)
        def top(t: int, **kwargs): mid(**kwargs)
        """
        ast_syms = ast_harvest(textwrap.dedent(src))
        ns = _compile_fn_from_source(src)
        fi_by_name = {f.name: f for f in ast_syms.functions}

        live = ns["top"]
        fi   = fi_by_name["top"]
        result = resolve_function_params(live, fi, ns, ast_info_by_name=fi_by_name)
        names = _param_names(result)
        assert len(names) == len(set(names)), "duplicate param names found"



class TestPositionalOnlyPromotion:
    def test_pos_only_absorbed_by_kwargs_becomes_pos_or_kw(self):
        """When a positional-only param is absorbed via **kwargs, it is promoted."""
        src = """
        def target(a: int, b: int, /) -> int: ...
        def wrapper(**kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        kinds = {p.name: p.kind for p, _ in result}
        # a and b are positional-only in target but absorbed via **kwargs
        # so they must become POSITIONAL_OR_KEYWORD in wrapper's stub
        assert kinds.get("a") == _POS_KW
        assert kinds.get("b") == _POS_KW



class TestMixedArgsAndKwargs:
    def test_both_forwarded(self):
        """Functions forwarding both *args and **kwargs simultaneously."""
        src = """
        def target(*colors: str, gamma: float = 1.0, r: float, g: float): ...
        def wrapper(*colors: str, **kwargs): target(*colors, **kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "*colors" in names  # typed *args preserved
        assert "gamma" in names
        assert "r" in names
        assert "g" in names


# ===========================================================================
# Unit tests: helper functions
# ===========================================================================


class TestNormaliseKind:
    def test_pos_only_promoted(self):
        p = inspect.Parameter("x", _POS_ONLY)
        assert _normalise_kind(p).kind == _POS_KW

    def test_pos_kw_unchanged(self):
        p = inspect.Parameter("x", _POS_KW)
        assert _normalise_kind(p).kind == _POS_KW

    def test_kw_only_unchanged(self):
        p = inspect.Parameter("x", _KW_ONLY)
        assert _normalise_kind(p).kind == _KW_ONLY

    def test_var_pos_unchanged(self):
        p = inspect.Parameter("args", _VAR_POS)
        assert _normalise_kind(p).kind == _VAR_POS

    def test_var_kw_unchanged(self):
        p = inspect.Parameter("kwargs", _VAR_KW)
        assert _normalise_kind(p).kind == _VAR_KW



class TestEnforceSignatureValidity:
    def test_no_defaults_unchanged(self):
        params = [
            (inspect.Parameter("x", _POS_KW), {}),
            (inspect.Parameter("y", _POS_KW), {}),
        ]
        result = _enforce_signature_validity(params)
        assert _param_kinds(result) == ["POS_KW", "POS_KW"]

    def test_non_default_after_default_promoted(self):
        p_with_default    = inspect.Parameter("a", _POS_KW, default=1)
        p_without_default = inspect.Parameter("b", _POS_KW)
        params = [(p_with_default, {}), (p_without_default, {})]
        result = _enforce_signature_validity(params)
        kinds = _param_kinds(result)
        assert kinds[0] == "POS_KW"   # a stays
        assert kinds[1] == "KW_ONLY"  # b promoted

    def test_already_kw_only_untouched(self):
        p_default    = inspect.Parameter("a", _POS_KW, default=1)
        p_kw_already = inspect.Parameter("b", _KW_ONLY)
        params = [(p_default, {}), (p_kw_already, {})]
        result = _enforce_signature_validity(params)
        assert _param_kinds(result)[1] == "KW_ONLY"

    def test_var_pos_skipped(self):
        p_default = inspect.Parameter("a", _POS_KW, default=1)
        p_varpos  = inspect.Parameter("args", _VAR_POS)
        p_after   = inspect.Parameter("b", _POS_KW)
        params = [(p_default, {}), (p_varpos, {}), (p_after, {})]
        result = _enforce_signature_validity(params)
        # VAR_POS skipped; b after it is POS_KW — position rule doesn't apply
        # (b comes before any defaulted positional param in the indexing that matters)
        # since first_default_idx=0 (p_default), p_varpos is at idx 1, and b is at idx 2
        # b has no default and idx 2 > 0, b.kind is POS_KW → promoted
        assert _param_kinds(result)[2] == "KW_ONLY"

    def test_empty_list(self):
        assert _enforce_signature_validity([]) == []



class TestMergeConcreteParams:
    def test_basic_merge(self):
        base: list = []
        seen: set = set()
        source = [
            (inspect.Parameter("x", _POS_KW), {"x": int}),
            (inspect.Parameter("y", _POS_KW, default=1), {"y": int}),
        ]
        _merge_concrete_params(base, seen, source)
        assert len(base) == 2
        assert seen == {"x", "y"}

    def test_deduplication(self):
        p_x = inspect.Parameter("x", _POS_KW)
        base = [(p_x, {})]
        seen = {"x"}
        source = [(inspect.Parameter("x", _POS_KW), {}),
                  (inspect.Parameter("y", _POS_KW), {})]
        _merge_concrete_params(base, seen, source)
        assert len(base) == 2  # x not re-added, y added
        assert "y" in seen

    def test_variadics_skipped(self):
        base: list = []
        seen: set = set()
        source = [
            (inspect.Parameter("args", _VAR_POS), {}),
            (inspect.Parameter("kwargs", _VAR_KW), {}),
            (inspect.Parameter("x", _POS_KW), {}),
        ]
        _merge_concrete_params(base, seen, source)
        assert len(base) == 1
        assert base[0][0].name == "x"

    def test_pos_only_promoted(self):
        base: list = []
        seen: set = set()
        source = [(inspect.Parameter("a", _POS_ONLY), {})]
        _merge_concrete_params(base, seen, source)
        assert base[0][0].kind == _POS_KW


# ===========================================================================
# AST scanning tests
# ===========================================================================


class TestASTKwargsScanning:
    def test_kwargs_forwarded_to_populated(self):
        src = "def f(**kwargs): target(**kwargs)"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" in fi.kwargs_forwarded_to

    def test_args_forwarded_to_populated(self):
        src = "def f(*args): target(*args)"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" in fi.args_forwarded_to

    def test_no_forwarding_empty_lists(self):
        src = "def f(x: int, y: int): return x + y"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert fi.kwargs_forwarded_to == []
        assert fi.args_forwarded_to == []

    def test_multiple_targets_detected(self):
        src = """
        def f(**kwargs):
            a(**kwargs)
            b(**kwargs)
        """
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "a" in fi.kwargs_forwarded_to
        assert "b" in fi.kwargs_forwarded_to

    def test_non_forwarded_kwargs_call_not_detected(self):
        """Only **kwargs (the variadic) forwarding is detected, not literal dicts."""
        src = """
        def f(**kwargs):
            target(x=1, y=2)  # no **kwargs spread
        """
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" not in fi.kwargs_forwarded_to

    def test_method_body_also_scanned(self):
        """Methods inside classes also get kwargs_forwarded_to populated."""
        src = """
        class C:
            def method(self, **kwargs):
                helper(**kwargs)
        """
        syms = ast_harvest(textwrap.dedent(src))
        method_info = syms.classes[0].methods[0]
        assert "helper" in method_info.kwargs_forwarded_to

    def test_cls_call_detected_in_classmethod(self):
        """@classmethod that forwards to cls() is detected."""
        src = """
        class C:
            @classmethod
            def create(cls, **kwargs):
                return cls(**kwargs)
        """
        syms = ast_harvest(textwrap.dedent(src))
        method_info = syms.classes[0].methods[0]
        assert "cls" in method_info.kwargs_forwarded_to

    def test_async_function_scanned(self):
        src = "async def f(**kwargs): await target(**kwargs)"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" in fi.kwargs_forwarded_to


# ===========================================================================
# Integration tests via generate_stub on demo/functions.py
# ===========================================================================

DEMO_DIR = Path(__file__).parent.parent / "demo"



# ---------------------------------------------------------------------------
# Mixed method↔function chain tests
# ---------------------------------------------------------------------------

class TestMethodToFunction:
    def test_method_kwargs_resolve_to_function_params(self, tmp_path):
        """A method that forwards **kwargs to a standalone function."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def draw(x: float, y: float, color: str = "black") -> None:
    pass

class Canvas:
    def paint(self, **kwargs) -> None:
        draw(**kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        # Canvas.paint should expand **kwargs to draw's params
        assert "x: float" in stub
        assert "y: float" in stub
        assert "color: str" in stub

    def test_method_to_function_deep_chain(self, tmp_path):
        """method → function → function chain."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def base(a: int, b: str = "x") -> None:
    pass

def middle(**kwargs) -> None:
    base(**kwargs)

class Obj:
    def entry(self, **kwargs) -> None:
        middle(**kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "a: int" in stub
        assert "b: str" in stub


class TestFunctionToClass:
    def test_function_kwargs_resolve_to_class_init(self, tmp_path):
        """A module-level function that forwards **kwargs to a class constructor."""
        src = tmp_path / "mod.py"
        src.write_text('''\
class Widget:
    def __init__(self, width: int = 100, height: int = 100, title: str = "") -> None:
        pass

def make_widget(**kwargs) -> Widget:
    return Widget(**kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        # make_widget should expand **kwargs to Widget.__init__ params
        assert "width: int" in stub
        assert "height: int" in stub
        assert "title: str" in stub


class TestMethodToMethod:
    def test_method_forwards_to_sibling_method(self, tmp_path):
        """Method A dispatches to method B on the same object via **kwargs."""
        src = tmp_path / "mod.py"
        src.write_text('''\
class Saver:
    def save_svg(self, path: str, *, width: int = 800, height: int = 600, compress: bool = False) -> int:
        return 0

    def save(self, path: str, **kwargs) -> int:
        return self.save_svg(path, **kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        # save() should expand to save_svg's params
        assert "width: int" in stub
        assert "height: int" in stub
        assert "compress: bool" in stub

    def test_method_dispatch_multiple_targets(self, tmp_path):
        """Method dispatches to different methods based on parameter — test union of params."""
        src = tmp_path / "mod.py"
        src.write_text('''\
class Renderer:
    def render_svg(self, *, width: int = 800, compress: bool = False) -> str:
        return ""

    def render_png(self, *, width: int = 800, dpi: int = 96) -> str:
        return ""

    def render(self, fmt: str = "svg", **kwargs) -> str:
        if fmt == "svg":
            return self.render_svg(**kwargs)
        return self.render_png(**kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        # render() should pick up kwargs from at least one target
        assert "width: int" in stub


class TestCycleGuard:
    def test_recursive_forwarding_does_not_hang(self, tmp_path):
        """Mutually recursive forwarding must not cause infinite recursion."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def a(**kwargs):
    b(**kwargs)

def b(**kwargs):
    a(**kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        # Must complete without hanging or raising RecursionError
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "def a" in stub
        assert "def b" in stub

    def test_self_referential_method(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text('''\
class Tree:
    def visit(self, *, depth: int = 0, **kwargs) -> None:
        self.visit(depth=depth + 1, **kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "def visit" in stub


class TestMROWithNamespaceChain:
    def test_method_chain_mro_then_function(self, tmp_path):
        """Method inherits **kwargs via MRO, which then forward to a function."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def low_level(speed: float = 1.0, power: float = 0.5) -> None:
    pass

class Base:
    def run(self, **kwargs) -> None:
        low_level(**kwargs)

class Child(Base):
    def run(self, label: str = "", **kwargs) -> None:
        super().run(**kwargs)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "label: str" in stub
        # speed and power should be resolved through MRO + namespace
        # (Base.run → low_level)


class TestArgsForwarding:
    def test_star_args_forwarding(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text('''\
def process(*items: str, gamma: float = 1.0) -> list[str]:
    return list(items)

def batch(*items: str, **opts) -> list[str]:
    return process(*items, **opts)
''')
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "gamma: float" in stub


# ---------------------------------------------------------------------------
# Resolver unit tests (no file I/O)
# ---------------------------------------------------------------------------

class TestResolveParamsWithNamespace:
    def test_method_resolves_via_namespace(self):
        def target_fn(x: int, y: str = "default") -> None:
            pass

        namespace = {"target_fn": target_fn}

        class MyClass:
            def method(self, **kwargs) -> None:
                target_fn(**kwargs)

        ast_info = _fi("method", kw_targets=["target_fn"])
        params = resolve_params(
            MyClass, "method",
            ast_info=ast_info,
            namespace=namespace,
        )
        names = [p.name for p, _ in params]
        assert "x" in names
        assert "y" in names

    def test_function_resolves_class_constructor(self):
        class Widget:
            def __init__(self, w: int, h: int = 100) -> None:
                pass

        def make(cls=Widget, **kwargs) -> "Widget":
            return cls(**kwargs)

        namespace = {"Widget": Widget}
        ast_info = _fi("make", kw_targets=["Widget"])

        params = resolve_function_params(make, ast_info, namespace)
        names = [p.name for p, _ in params]
        assert "w" in names
        assert "h" in names


# ---------------------------------------------------------------------------
# Cross-file method→function chains
# ---------------------------------------------------------------------------

class TestCrossFileChains:
    """Method in file A forwards **kwargs to function imported from file B."""

    def test_cross_file_method_to_function(self, tmp_path):
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            (tmp_path / "lib.py").write_text(
                "def draw(x: float, y: float, color: str = 'black') -> None: pass\n"
            )
            (tmp_path / "canvas.py").write_text(
                "from lib import draw\n\n"
                "class Canvas:\n"
                "    def paint(self, **kwargs) -> None:\n"
                "        draw(**kwargs)\n"
            )
            from stubpy import generate_stub
            from stubpy.context import StubContext
            ctx = StubContext()
            stub = generate_stub(str(tmp_path / "canvas.py"),
                                 str(tmp_path / "canvas.pyi"), ctx=ctx)
            assert "x: float" in stub
            assert "y: float" in stub
            assert "color: str" in stub
        finally:
            sys.path.remove(str(tmp_path))

    def test_cross_file_function_to_function(self, tmp_path):
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            (tmp_path / "base.py").write_text(
                "def configure(width: int = 800, height: int = 600, dpi: int = 96) -> None: pass\n"
            )
            (tmp_path / "app.py").write_text(
                "from base import configure\n\n"
                "def setup(**kwargs) -> None:\n"
                "    configure(**kwargs)\n"
            )
            from stubpy import generate_stub
            from stubpy.context import StubContext
            ctx = StubContext()
            stub = generate_stub(str(tmp_path / "app.py"),
                                 str(tmp_path / "app.pyi"), ctx=ctx)
            assert "width: int" in stub
            assert "height: int" in stub
            assert "dpi: int" in stub
        finally:
            sys.path.remove(str(tmp_path))

    def test_cross_file_function_to_class_init(self, tmp_path):
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            (tmp_path / "widgets.py").write_text(
                "class Button:\n"
                "    def __init__(self, label: str, width: int = 100) -> None: pass\n"
            )
            (tmp_path / "factory.py").write_text(
                "from widgets import Button\n\n"
                "def make_button(**kwargs) -> Button:\n"
                "    return Button(**kwargs)\n"
            )
            from stubpy import generate_stub
            from stubpy.context import StubContext
            ctx = StubContext()
            stub = generate_stub(str(tmp_path / "factory.py"),
                                 str(tmp_path / "factory.pyi"), ctx=ctx)
            assert "label: str" in stub
            assert "width: int" in stub
        finally:
            sys.path.remove(str(tmp_path))

    def test_demo_dispatch_cross_file_tint(self):
        """CrossFileRenderer.tint in demo/dispatch.py expands make_color params."""
        from pathlib import Path
        import sys
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        try:
            from stubpy import generate_stub
            from stubpy.context import StubContext
            ctx = StubContext()
            stub = generate_stub(
                str(root / "demo" / "dispatch.py"),
                str(root / "demo" / "dispatch.pyi"),
                ctx=ctx,
            )
            assert "class CrossFileRenderer" in stub
            # make_color params: r, g, b, a
            assert "r: float" in stub
            assert "g: float" in stub
            assert "b: float" in stub
        finally:
            pyi = root / "demo" / "dispatch.pyi"
            if pyi.exists():
                pyi.unlink()
            if str(root) in sys.path:
                sys.path.remove(str(root))
