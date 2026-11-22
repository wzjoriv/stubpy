"""The compiled type mapper keeps names a hand-written stub imports instead of guessing a module."""
from __future__ import annotations

from stubpy.compiled.typemap import TypeMapper


def test_known_alias_import_is_kept():
    mapper = TypeMapper("pkg._ext", set(), {"npt": "import numpy.typing as npt"})
    assert mapper("npt.NDArray") == "npt.NDArray"
    assert mapper.imports == {"npt": "import numpy.typing as npt"}


def test_module_imported_through_another_module_is_imported_directly():
    mapper = TypeMapper("pkg._ext", set(), {"abc_mod": "from importlib import abc as abc_mod"})
    mapper("abc_mod.Loader")
    assert mapper.imports == {"abc_mod": "import importlib.abc as abc_mod"}


def test_unknown_root_still_guesses_a_module():
    mapper = TypeMapper("pkg._ext")
    mapper("npt.NDArray")
    assert mapper.imports == {"npt": "import npt"}


def test_foreign_type_alias_becomes_an_import():
    import sys

    import pytest

    if sys.version_info < (3, 12):
        pytest.skip("TypeAliasType needs Python 3.12")
    from typing import TypeAliasType

    from stubpy.compiled.introspect import _foreign_type_alias

    alias = TypeAliasType("Grid", list[int])
    alias_home = alias.__module__
    assert _foreign_type_alias("Grid", alias, "pkg._ext") == f"from {alias_home} import Grid"
    assert _foreign_type_alias("Other", alias, "pkg._ext") is None
    assert _foreign_type_alias("Grid", alias, alias_home) is None
