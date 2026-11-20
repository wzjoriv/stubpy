"""
Aliases from private modules are inlined; public and exported ones keep their names.
"""
from __future__ import annotations

import stubpy
from stubpy.core.context import StubContext
from stubpy.emit.annotations.private_aliases import inline_private_aliases, is_private_module
from tests.conftest import flatten, write_tree

FILES = {
    "pkg/__init__.py": "",
    "pkg/_hidden.py": "Mode = bool | str\nPair = tuple[int, int]\n",
    "pkg/_shared.py": "__all__ = ['Exported']\nExported = int | bytes\n",
    "pkg/kinds.py": "Public = int | str\n",
    "pkg/api.py": """
        from . import _hidden as _h
        from ._hidden import Pair
        from ._shared import Exported
        from .kinds import Public

        LEVEL: _h.Mode = True


        def run(mode: _h.Mode = True, pair: Pair | None = None, pub: Public = 1, ex: Exported = 1) -> None:
            pass


        class Holder:
            mode: _h.Mode = True

            def __init__(self, flag: _h.Mode = False) -> None:
                self.flag: _h.Mode = flag
    """,
}


def test_private_aliases_are_inlined(tmp_path):
    write_tree(tmp_path, FILES)
    stub = flatten(stubpy.render(str(tmp_path / "pkg" / "api.py")).text)
    assert "mode: bool | str = True" in stub
    assert "pair: tuple[int, int] | None = None" in stub
    assert "pub: Public = 1" in stub and "from .kinds import Public" in stub
    assert "ex: Exported = 1" in stub and "from ._shared import Exported" in stub
    assert "LEVEL: bool | str" in stub
    assert "    mode: bool | str" in stub and "    flag: bool | str" in stub
    assert "_hidden" not in stub


def test_helpers():
    assert is_private_module("pkg._hidden") and is_private_module("_pkg.mod")
    assert not is_private_module("pkg.kinds") and not is_private_module("__main__")
    assert inline_private_aliases("int | None", {}, StubContext()) == "int | None"
