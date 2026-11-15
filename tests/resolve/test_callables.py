"""Tests for stubpy.resolve.callables: unwrapping and run-scoped caches."""
from __future__ import annotations

import functools

from stubpy.resolve import (
    function_info_of,
    hints_of,
    introspection_cache,
    signature_of,
    unwrap_callable,
)


def target(a: int, b: str = "x", *, c: float = 1.0) -> bool: ...


def _wrap(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


class FakeDispatcher:
    """Mimics a numba ``Dispatcher``: callable, with the Python function in ``py_func``."""

    def __init__(self, fn):
        self.py_func = fn

    def __call__(self, *args, **kwargs):
        return self.py_func(*args, **kwargs)


class TestUnwrapCallable:
    def test_wraps_chain(self):
        assert unwrap_callable(_wrap(_wrap(target))) is target

    def test_lru_cache(self):
        assert unwrap_callable(functools.lru_cache(maxsize=None)(target)) is target

    def test_staticmethod_and_classmethod(self):
        assert unwrap_callable(staticmethod(target)) is target
        assert unwrap_callable(classmethod(target)) is target

    def test_numba_like_dispatcher(self):
        assert unwrap_callable(FakeDispatcher(target)) is target

    def test_wrapped_cycle_terminates(self):
        def a(): ...
        def b(): ...
        a.__wrapped__ = b
        b.__wrapped__ = a
        assert unwrap_callable(a) in (a, b)
        assert signature_of(a) is not None

    def test_partial_and_class_are_kept(self):
        p = functools.partial(target, 1)
        assert unwrap_callable(p) is p
        assert unwrap_callable(FakeDispatcher) is FakeDispatcher

    def test_attribute_errors_are_ignored(self):
        class Hostile:
            def __getattr__(self, name):
                raise RuntimeError(name)

            def __call__(self): ...
        obj = Hostile()
        assert unwrap_callable(obj) is obj


class TestSignatureOf:
    def test_partial_removes_bound_arguments(self):
        sig = signature_of(functools.partial(_wrap(target), 1, c=2.0))
        assert list(sig.parameters) == ["b", "c"]
        assert sig.parameters["c"].default == 2.0

    def test_dispatcher_signature(self):
        assert list(signature_of(FakeDispatcher(target)).parameters) == ["a", "b", "c"]

    def test_bound_method_drops_receiver(self):
        class K:
            def m(self, x: int) -> None: ...
        assert list(signature_of(K().m).parameters) == ["x"]

    def test_uninspectable_gives_none(self):
        assert signature_of(42) is None


class TestHintsAndCache:
    def test_hints_resolve_through_wrappers(self):
        assert hints_of(_wrap(target))["return"] is bool

    def test_cache_returns_same_object_inside_block(self):
        with introspection_cache():
            assert signature_of(target) is signature_of(target)
            assert hints_of(target) is hints_of(target)

    def test_nested_blocks_share_the_outer_cache(self):
        with introspection_cache():
            first = signature_of(target)
            with introspection_cache():
                assert signature_of(target) is first

    def test_function_info_from_source(self):
        def forwarder(**kw):
            kw.pop("x", 1)
            return target(**kw)
        info = function_info_of(_wrap(forwarder))
        assert info.kwargs_forwarded_to == ["target"]
        assert info.kwargs_consumed == {"x": "1"}
