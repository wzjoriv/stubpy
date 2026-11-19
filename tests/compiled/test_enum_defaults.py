"""Enum defaults of compiled callables import their class even when nothing else does."""
from __future__ import annotations

import enum
import inspect
import sys
import types

import pytest

from stubpy.compiled.signatures.sources import value_text

from .fakes import FakeBuiltin, fake_module
from .test_introspect import _render


class Light(enum.Enum):
    ON = 1
    OFF = 0


@pytest.fixture
def other(monkeypatch):
    module = types.ModuleType("otherext_pkg.lights")
    package = types.ModuleType("otherext_pkg")
    package.__path__ = []
    monkeypatch.setattr(Light, "__module__", "otherext_pkg.lights")
    module.Light = Light
    monkeypatch.setitem(sys.modules, "otherext_pkg", package)
    monkeypatch.setitem(sys.modules, "otherext_pkg.lights", module)
    return module


def test_docstring_default_is_qualified_from_the_annotation(other):
    text, _ = _render(fake_module(glow=FakeBuiltin("glow", "glow(light: otherext_pkg.lights.Light = <Light.ON: 1>)")))
    assert "def glow(light: otherext_pkg.lights.Light = otherext_pkg.lights.Light.ON)" in text
    assert text.count("import otherext_pkg.lights\n") == 1


def test_live_default_is_qualified_from_the_object(other):
    def dim(level=Light.OFF): ...
    fn = FakeBuiltin("dim", "No signature line.")
    fn.__signature__ = inspect.signature(dim)
    text, _ = _render(fake_module(dim=fn))
    assert "level=otherext_pkg.lights.Light.OFF" in text.replace(" ", "")
    assert "import otherext_pkg.lights" in text


def test_value_text():
    assert value_text(Light.ON).endswith("Light.ON")
    assert value_text(3) == "3"
