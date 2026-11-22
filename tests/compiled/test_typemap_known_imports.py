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
