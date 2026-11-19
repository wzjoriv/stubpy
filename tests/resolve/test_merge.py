"""Tests for the parameter-merging helpers."""
from __future__ import annotations

import inspect

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS
from stubpy.resolve._merge import enforce_signature_validity, merge_concrete_params
from tests.conftest import _param_kinds


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

    def test_pos_only_kept_at_the_front(self):
        base: list = []
        seen: set = set()
        source = [(inspect.Parameter("a", POS_ONLY), {})]
        merge_concrete_params(base, seen, source)
        assert base[0][0].kind == POS_ONLY

    def test_pos_only_makes_earlier_positionals_pos_only(self):
        base: list = [(inspect.Parameter("x", POS_KW), {})]
        seen: set = {"x"}
        source = [(inspect.Parameter("a", POS_ONLY), {})]
        merge_concrete_params(base, seen, source)
        assert [p.kind for p, _ in base] == [POS_ONLY, POS_ONLY]

    def test_pos_only_after_keyword_only_stays_pos_only(self):
        base: list = [(inspect.Parameter("k", KW_ONLY), {})]
        merge_concrete_params(base, {"k"}, [(inspect.Parameter("a", POS_ONLY), {})])
        assert base[1][0].kind == POS_ONLY
