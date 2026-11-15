"""Tests for register_annotation_handler."""
from __future__ import annotations

import pytest

from stubpy.core.context import StubContext
from stubpy.emit.annotations import (
    annotation_to_str,
    register_annotation_handler,
)
from stubpy.emit.annotations.registry import ANNOTATION_HANDLERS
from tests.conftest import _ctx


@pytest.fixture
def ctx() -> StubContext:
    return StubContext()


class TestRegisterAnnotationHandler:
    def test_custom_handler_appended(self):
        initial_count = len(ANNOTATION_HANDLERS)

        class _Sentinel:
            pass

        @register_annotation_handler(lambda a: isinstance(a, _Sentinel))
        def _handle_sentinel(ann, ctx):
            return "Sentinel"

        assert len(ANNOTATION_HANDLERS) == initial_count + 1
        ANNOTATION_HANDLERS.pop()

    def test_custom_handler_called(self):
        class MyWrapper:
            def __init__(self, inner):
                self.inner = inner

        @register_annotation_handler(lambda a: isinstance(a, MyWrapper))
        def _handle_wrapper(ann, ctx):
            inner_str = annotation_to_str(ann.inner, ctx)
            return f"MyWrapper[{inner_str}]"

        ctx = _ctx()
        result = annotation_to_str(MyWrapper(int), ctx)
        assert result == "MyWrapper[int]"
        ANNOTATION_HANDLERS.pop()

    def test_returns_handler_unchanged(self):
        def my_handler(ann, ctx):
            return "x"

        decorated = register_annotation_handler(lambda a: False)(my_handler)
        assert decorated is my_handler
        ANNOTATION_HANDLERS.pop()

    def test_register_annotation_handler_exported_from_extend(self):
        from stubpy.extend import register_annotation_handler as rah
        assert rah is register_annotation_handler

    def test_first_puts_handler_ahead_of_builtins(self):
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str

        @register_annotation_handler(lambda a: a is int, first=True)
        def _int(ann, ctx):
            return "Integer"
        try:
            assert ANNOTATION_HANDLERS[0][1] is _int
            assert annotation_to_str(int, StubContext()) == "Integer"
        finally:
            ANNOTATION_HANDLERS.pop(0)
        assert annotation_to_str(int, StubContext()) == "int"
