"""Public hooks: forwarding-target resolvers and stub text hooks."""
from __future__ import annotations

import pytest

from stubpy import Config, render
from stubpy.extend import register_forward_resolver, register_stub_hook
from stubpy.state import hooks

SOURCE = '''\
def _draw(x: int, color: str = "red") -> None: ...

def plot(**kwargs):
    return backend_draw(**kwargs)
'''


@pytest.fixture(autouse=True)
def _clean():
    yield
    hooks.FORWARD_RESOLVERS.clear()
    hooks.STUB_HOOKS.clear()


def test_forward_resolver(tmp_path):
    src = tmp_path / "plotting.py"
    src.write_text(SOURCE)
    assert "def plot(**kwargs)" in render(src).text

    @register_forward_resolver
    def backend(name, namespace):
        return namespace["_draw"] if name == "backend_draw" else None

    assert "    x: int,\n    color: str = 'red',\n" in render(src).text


def test_stub_hook(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text("x: int = 1\n")
    register_stub_hook(lambda text, ctx: "# generated\n" + text.replace("int", "float"))
    assert render(src, config=Config(imports="none")).text == "# generated\nx: float\n"
