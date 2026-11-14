"""Tests for **kwargs / *args forwarding detection in the harvester."""
from __future__ import annotations

import textwrap

from stubpy.analysis.harvest import ast_harvest


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
