"""Qualified binding type names mapped to stub annotations and imports."""
from __future__ import annotations

import pytest

from stubpy.compiled.signatures import normalize_type, parse_signature
from stubpy.compiled.typemap import TypeMapper, portable_annotation


@pytest.fixture
def mapper() -> TypeMapper:
    return TypeMapper("pkg._ext", {"Mode", "Light", "Sequence"})


def test_own_module_names_are_bare(mapper):
    assert mapper("pkg._ext.Mode") == "Mode"
    assert mapper("pkg._ext.Light.Kind") == "Light.Kind"
    assert mapper.imports == {}


def test_typing_names_become_bare_with_imports(mapper):
    assert mapper("typing.SupportsFloat | typing.SupportsIndex") == "SupportsFloat | SupportsIndex"
    assert mapper.imports["SupportsIndex"] == "from typing import SupportsIndex"


def test_collections_abc_name_clashing_with_a_local_stays_qualified(mapper):
    assert mapper("collections.abc.Sequence[float]") == "collections.abc.Sequence[float]"
    assert mapper.imports["collections.abc"] == "import collections.abc"


def test_other_modules_stay_qualified(mapper):
    assert mapper("numpy.typing.NDArray[numpy.float32]") == "numpy.typing.NDArray[numpy.float32]"
    assert {"numpy", "numpy.typing"} <= set(mapper.imports)


def test_builtins_prefix_dropped(mapper):
    assert mapper("builtins.int") == "int"


def test_unknown_bare_names_become_any(mapper):
    assert mapper("list[Py_UCS4]") == "list[Any]"


def test_annotated_metadata_kept(mapper):
    assert mapper('typing.Annotated[list[float], "FixedSize(3)"]') == "Annotated[list[float], 'FixedSize(3)']"


def test_garbage_is_none(mapper):
    assert mapper("not valid [") is None and mapper(None) is None


def test_portable_annotation():
    assert portable_annotation("typing.Optional[int]") == "Optional[int]"
    assert portable_annotation("numpy.ndarray") is None


class TestBindingTypeText:
    def test_nanobind_ndarray(self):
        text = "numpy.ndarray[dtype=float32, shape=(*, *, 4), order='C', device='cpu']"
        assert normalize_type(text) == "numpy.typing.NDArray[numpy.float32]"
        assert normalize_type("ndarray[shape=(*, 2)]") == "numpy.typing.NDArray[typing.Any]"
        assert normalize_type("list[numpy.ndarray]") == "list[numpy.ndarray]"

    def test_cython_memoryview_and_void(self):
        parsed = parse_signature("fill(float[:, :, ::1] out, double[::1] w, int n=2) -> void")
        assert parsed is not None
        assert parsed[1].render() == "(out: typing_extensions.Buffer, w: typing_extensions.Buffer, n: int = 2) -> None"

    def test_owner_qualified_cython_method(self):
        from stubpy.compiled.signatures import docstring_signatures, strip_signature_lines

        doc = "Lut.sample(self, double t, int spread=PAD) -> tuple\n\nThe color at t."
        sigs = docstring_signatures("sample", doc)
        assert [s.names for s in sigs] == [("self", "t", "spread")]
        assert strip_signature_lines("sample", doc) == "The color at t."
