"""
tests/test_aliases.py
---------------------
Unit tests for stubpy.aliases:
  - _is_type_alias
  - build_alias_registry
"""
from __future__ import annotations

import types as _builtin_types
import typing
from typing import List, Literal, Optional, Sequence, Tuple, Union

import pytest

from stubpy.aliases import _is_type_alias, build_alias_registry
from stubpy.context import StubContext


# ---------------------------------------------------------------------------
# _is_type_alias
# ---------------------------------------------------------------------------

class TestIsTypeAlias:
    # ── things that ARE aliases ──────────────────────────────────────────
    def test_pep604_union(self):
        assert _is_type_alias(str | int | float) is True

    def test_pep604_optional(self):
        assert _is_type_alias(str | None) is True

    def test_subscripted_list(self):
        assert _is_type_alias(List[str]) is True

    def test_subscripted_tuple(self):
        assert _is_type_alias(Tuple[float, float]) is True

    def test_subscripted_union(self):
        assert _is_type_alias(Union[str, int]) is True

    def test_subscripted_literal(self):
        assert _is_type_alias(Literal["a", "b"]) is True

    def test_subscripted_sequence(self):
        assert _is_type_alias(Sequence[int]) is True

    # ── things that are NOT aliases ──────────────────────────────────────
    def test_plain_class(self):
        class MyClass:
            pass
        assert _is_type_alias(MyClass) is False

    def test_builtin_type(self):
        assert _is_type_alias(int) is False
        assert _is_type_alias(str) is False

    def test_module(self):
        import os
        assert _is_type_alias(os) is False

    def test_none(self):
        assert _is_type_alias(None) is False

    def test_bare_list_unsubscripted(self):
        # bare List has no __args__ — not an alias
        assert _is_type_alias(List) is False

    def test_bare_optional_unsubscripted(self):
        assert _is_type_alias(Optional) is False


# ---------------------------------------------------------------------------
# build_alias_registry
# ---------------------------------------------------------------------------

class TestBuildAliasRegistry:
    def _make_module_with_types_submodule(self):
        """
        Build a minimal fake module that has a `types` attribute which is
        itself a module containing type aliases.
        """
        types_mod = _builtin_types.ModuleType("faketypes")
        types_mod.Length = str | float | int            # type: ignore[attr-defined]
        types_mod.Color  = str | Tuple[float, float, float]  # type: ignore[attr-defined]
        types_mod.Cap    = Literal["butt", "round"]     # type: ignore[attr-defined]
        types_mod.Number = int | float                   # type: ignore[attr-defined]

        parent_mod = _builtin_types.ModuleType("fakeparent")
        parent_mod.types = types_mod                    # type: ignore[attr-defined]
        return parent_mod

    def test_aliases_registered(self):
        module = self._make_module_with_types_submodule()
        import_map = {"types": "from fake import types"}
        ctx = StubContext()
        build_alias_registry(module, import_map, ctx)
        alias_strs = [e.alias_str for e in ctx.alias_registry]
        assert "types.Length" in alias_strs
        assert "types.Color"  in alias_strs
        assert "types.Cap"    in alias_strs
        assert "types.Number" in alias_strs

    def test_type_module_import_recorded(self):
        module = self._make_module_with_types_submodule()
        import_map = {"types": "from fake import types"}
        ctx = StubContext()
        build_alias_registry(module, import_map, ctx)
        assert ctx.type_module_imports.get("types") == "from fake import types"

    def test_no_aliases_no_import_recorded(self):
        """If a sub-module has no type aliases, its import is not recorded."""
        empty_mod = _builtin_types.ModuleType("emptymod")
        parent_mod = _builtin_types.ModuleType("parent")
        parent_mod.empty = empty_mod                    # type: ignore[attr-defined]

        import_map = {"empty": "from x import empty"}
        ctx = StubContext()
        build_alias_registry(parent_mod, import_map, ctx)
        assert ctx.type_module_imports == {}
        assert ctx.alias_registry == []

    def test_private_attributes_skipped(self):
        """Names starting with _ are not treated as aliases."""
        types_mod = _builtin_types.ModuleType("t")
        types_mod._private = str | int                  # type: ignore[attr-defined]
        types_mod.Public   = str | int                  # type: ignore[attr-defined]

        parent_mod = _builtin_types.ModuleType("p")
        parent_mod.t = types_mod                        # type: ignore[attr-defined]

        import_map = {"t": "from x import t"}
        ctx = StubContext()
        build_alias_registry(parent_mod, import_map, ctx)
        alias_strs = [e.alias_str for e in ctx.alias_registry]
        assert "t.Public"   in alias_strs
        assert "t._private" not in alias_strs

    def test_non_module_attributes_ignored(self):
        """Plain class / function attributes on the parent are not scanned."""
        class NotAModule:
            Length = str | int
        parent_mod = _builtin_types.ModuleType("p")
        parent_mod.things = NotAModule                  # type: ignore[attr-defined]

        import_map = {"things": "from x import things"}
        ctx = StubContext()
        build_alias_registry(parent_mod, import_map, ctx)
        assert ctx.alias_registry == []

    def test_lookup_after_build(self):
        module = self._make_module_with_types_submodule()
        import_map = {"types": "from fake import types"}
        ctx = StubContext()
        build_alias_registry(module, import_map, ctx)

        length_alias = str | float | int
        result = ctx.lookup_alias(length_alias)
        assert result == "types.Length"

    def test_lookup_marks_module_used(self):
        module = self._make_module_with_types_submodule()
        import_map = {"types": "from fake import types"}
        ctx = StubContext()
        build_alias_registry(module, import_map, ctx)

        ctx.lookup_alias(str | float | int)
        assert "types" in ctx.used_type_imports

    def test_unknown_annotation_not_aliased(self):
        module = self._make_module_with_types_submodule()
        import_map = {"types": "from fake import types"}
        ctx = StubContext()
        build_alias_registry(module, import_map, ctx)

        result = ctx.lookup_alias(bool | None)
        assert result is None
