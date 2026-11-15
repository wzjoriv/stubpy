"""Tests for the parameter-merging helpers."""
from __future__ import annotations

import inspect

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS
from stubpy.resolve._merge import enforce_signature_validity, merge_concrete_params, normalise_kind
from tests.conftest import _param_kinds


class TestNormaliseKind:
    def test_pos_only_promoted(self):
        p = inspect.Parameter("x", POS_ONLY)
        assert normalise_kind(p).kind == POS_KW

    def test_pos_kw_unchanged(self):
        p = inspect.Parameter("x", POS_KW)
        assert normalise_kind(p).kind == POS_KW

    def test_kw_only_unchanged(self):
        p = inspect.Parameter("x", KW_ONLY)
        assert normalise_kind(p).kind == KW_ONLY

    def test_var_pos_unchanged(self):
        p = inspect.Parameter("args", VAR_POS)
        assert normalise_kind(p).kind == VAR_POS

    def test_var_kw_unchanged(self):
        p = inspect.Parameter("kwargs", VAR_KW)
        assert normalise_kind(p).kind == VAR_KW


class TestEnforceSignatureValidity:
    def test_no_defaults_unchanged(self):
        params = [
            (inspect.Parameter("x", POS_KW), {}),
            (inspect.Parameter("y", POS_KW), {}),
        ]
        result = enforce_signature_validity(params)
        assert _param_kinds(result) == ["POS_KW", "POS_KW"]

    def test_non_default_after_default_promoted(self):
        p_with_default    = inspect.Parameter("a", POS_KW, default=1)
        p_without_default = inspect.Parameter("b", POS_KW)
        params = [(p_with_default, {}), (p_without_default, {})]
        result = enforce_signature_validity(params)
        kinds = _param_kinds(result)
        assert kinds[0] == "POS_KW"
        assert kinds[1] == "KW_ONLY"

    def test_already_kw_only_untouched(self):
        p_default    = inspect.Parameter("a", POS_KW, default=1)
        p_kw_already = inspect.Parameter("b", KW_ONLY)
        params = [(p_default, {}), (p_kw_already, {})]
        result = enforce_signature_validity(params)
        assert _param_kinds(result)[1] == "KW_ONLY"

    def test_var_pos_skipped(self):
        p_default = inspect.Parameter("a", POS_KW, default=1)
        p_varpos  = inspect.Parameter("args", VAR_POS)
        p_after   = inspect.Parameter("b", POS_KW)
        params = [(p_default, {}), (p_varpos, {}), (p_after, {})]
        result = enforce_signature_validity(params)
        assert _param_kinds(result)[2] == "KW_ONLY"

    def test_empty_list(self):
        assert enforce_signature_validity([]) == []


class TestMergeConcreteParams:
    def test_basic_merge(self):
        base: list = []
        seen: set = set()
        source = [
            (inspect.Parameter("x", POS_KW), {"x": int}),
            (inspect.Parameter("y", POS_KW, default=1), {"y": int}),
        ]
        merge_concrete_params(base, seen, source)
        assert len(base) == 2
        assert seen == {"x", "y"}

    def test_deduplication(self):
        p_x = inspect.Parameter("x", POS_KW)
        base = [(p_x, {})]
        seen = {"x"}
        source = [(inspect.Parameter("x", POS_KW), {}),
                  (inspect.Parameter("y", POS_KW), {})]
        merge_concrete_params(base, seen, source)
        assert len(base) == 2
        assert "y" in seen

    def test_variadics_skipped(self):
        base: list = []
        seen: set = set()
        source = [
            (inspect.Parameter("args", VAR_POS), {}),
            (inspect.Parameter("kwargs", VAR_KW), {}),
            (inspect.Parameter("x", POS_KW), {}),
        ]
        merge_concrete_params(base, seen, source)
        assert len(base) == 1
        assert base[0][0].name == "x"

    def test_pos_only_promoted(self):
        base: list = []
        seen: set = set()
        source = [(inspect.Parameter("a", POS_ONLY), {})]
        merge_concrete_params(base, seen, source)
        assert base[0][0].kind == POS_KW
