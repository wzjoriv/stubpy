from __future__ import annotations

import ast
import inspect
import sys

import pytest

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS
from stubpy.compiled.signatures import (
    Param,
    Signature,
    docstring_signatures,
    from_inspect,
    nanobind_signatures,
    normalize_type,
    parse_signature,
    signatures_of,
    strip_signature_lines,
)


def _render(text: str) -> str:
    parsed = parse_signature(text)
    assert parsed is not None
    return parsed[1].render()


def _valid(sig_text: str) -> None:
    ast.parse(f"def f{sig_text}: ...")


class TestParseSignature:
    def test_pybind_typed(self):
        out = _render("distance(a: geom._vec.Point, b: geom._vec.Point) -> float")
        assert out == "(a: geom._vec.Point, b: geom._vec.Point) -> float"

    def test_text_signature_pseudo_params_dropped(self):
        assert _render("dot($module, a, b, /)") == "(a, b, /)"
        assert _render("scale($self, /, factor, inplace=False)") == "(factor, inplace=False)"

    def test_positional_only_marker(self):
        parsed = parse_signature("f(a, b, /, c)")
        assert parsed is not None
        kinds = [p.kind for p in parsed[1].params]
        assert kinds == [POS_ONLY, POS_ONLY, POS_KW]

    def test_keyword_only_after_star(self):
        parsed = parse_signature("centroid(points, *, weighted=False, weights=None)")
        assert parsed is not None
        assert [p.kind for p in parsed[1].params] == [POS_KW, KW_ONLY, KW_ONLY]
        assert parsed[1].render() == "(points, *, weighted=False, weights=None)"

    def test_varargs_make_following_keyword_only(self):
        parsed = parse_signature("f(*args, key=None, **kwargs)")
        assert parsed is not None
        assert [p.kind for p in parsed[1].params] == [VAR_POS, KW_ONLY, VAR_KW]

    def test_def_prefix_and_trailing_colon(self):
        assert _render("def clamp(x: float, lo: float = 0.0) -> float:") == "(x: float, lo: float = 0.0) -> float"

    def test_qualified_name_uses_last_part(self):
        parsed = parse_signature("pkg.mod.func(x)")
        assert parsed is not None and parsed[0] == "func"

    def test_cython_c_style_types(self):
        assert _render("Vec2(double x=0.0, double y=0.0, str label='')") == (
            "(x: float = 0.0, y: float = 0.0, label: str = '')"
        )

    def test_cython_bint_and_extension_type(self):
        assert _render("dot(Vec2 a, Vec2 b)") == "(a: Vec2, b: Vec2)"
        assert _render("f(bint flag, Py_ssize_t n)") == "(flag: bool, n: int)"

    def test_cython_unsigned_multiword_type(self):
        assert _render("f(unsigned long n)") == "(n: int)"

    def test_cython_hidden_default(self):
        assert _render("f(x, y=*)") == "(x, y=...)"

    def test_object_repr_default_becomes_ellipsis(self):
        assert _render("f(x: object = <object object at 0x0000>)") == "(x: object = ...)"
        assert _render("f(m: Mode = <Mode.FAST: 1>)") == "(m: Mode = Mode.FAST)"
        assert _render("f(m: Mode = <Mode at 0x1>)") == "(m: Mode = ...)"

    def test_dotted_default_kept(self):
        assert _render("f(m: Mode = Mode.FAST)") == "(m: Mode = Mode.FAST)"

    def test_bare_name_default_is_ellipsis(self):
        assert _render("f(x=inf)") == "(x=...)"
        assert _render("f(x=SOME_CONST)") == "(x=...)"

    def test_string_default_with_comma_and_parens(self):
        assert _render("f(sep=', (x)')") == "(sep=', (x)')"

    def test_nested_generic_with_commas(self):
        assert _render("f(m: Dict[str, List[int]]) -> Tuple[int, str]") == (
            "(m: dict[str, list[int]]) -> tuple[int, str]"
        )

    def test_invalid_annotation_dropped(self):
        parsed = parse_signature("f(x: numpy.ndarray[float64, flags.c_contiguous])")
        assert parsed is not None
        assert parsed[1].params[0].annotation in (None, "numpy.ndarray[float64, flags.c_contiguous]")

    @pytest.mark.parametrize("text", ["", "noparens", "(x)", "f(x", "1f(x)", "f(1bad)"])
    def test_garbage_returns_none(self, text):
        assert parse_signature(text) is None

    def test_empty_params(self):
        assert _render("version() -> str") == "() -> str"

    def test_rendered_signatures_parse(self):
        for text in [
            "a(x, /, y, *, z=1)", "b(*args, **kwargs)", "c(double x=0.0, *, bint fast=True)",
            "d(self: P, other: P) -> P", "e(p, /)", "f(*, k)",
        ]:
            _valid(_render(text))


class TestDocstringSignatures:
    PYBIND_OVERLOADED = (
        "distance(*args, **kwargs)\n"
        "Overloaded function.\n\n"
        "1. distance(a: geom._vec.Point, b: geom._vec.Point) -> float\n\n"
        "Euclidean distance between two points.\n\n"
        "2. distance(x1: float, y1: float, x2: float, y2: float) -> float\n\n"
        "Euclidean distance between two coordinate pairs.\n"
    )

    def test_pybind_overloads(self):
        sigs = docstring_signatures("distance", self.PYBIND_OVERLOADED)
        assert [s.names for s in sigs] == [("a", "b"), ("x1", "y1", "x2", "y2")]
        assert all(s.returns == "float" for s in sigs)

    def test_pybind_overloads_strip(self):
        body = strip_signature_lines("distance", self.PYBIND_OVERLOADED)
        assert "Euclidean distance between two points." in body
        assert "distance(" not in body and "Overloaded" not in body

    def test_single_signature_first_line(self):
        doc = "cross(a, b) -> Vec3\n\nCross product of two 3-vectors."
        sigs = docstring_signatures("cross", doc)
        assert len(sigs) == 1 and sigs[0].returns == "Vec3"
        assert strip_signature_lines("cross", doc) == "Cross product of two 3-vectors."

    def test_nanobind_multiple_lines(self):
        doc = (
            "side(segment: S, point: V, *, eps: float = 1e-12) -> Side\n"
            "side(segment: S, x: float, y: float, *, eps: float = 1e-12) -> Side\n\n"
            "Which side."
        )
        assert len(docstring_signatures("side", doc)) == 2

    def test_other_name_ignored(self):
        assert docstring_signatures("foo", "bar(x)\n\nDoc.") == []

    def test_no_doc(self):
        assert docstring_signatures("f", None) == []
        assert strip_signature_lines("f", None) == ""

    def test_text_signature_separator_removed(self):
        assert strip_signature_lines("dot", "dot($module, a, b, /)\n--\n\nDot product.") == "Dot product."


class _NB:
    def __init__(self, entries):
        self.__nb_signature__ = entries
        self.__name__ = "side"


class TestNanobind:
    def test_placeholders_filled_from_defaults(self):
        obj = _NB((("def clamp(x: float, lo: float = \\0, hi: float = \\1) -> float", "doc", (0.0, 1.0)),))
        (sig,) = nanobind_signatures(obj)
        assert sig.render() == "(x: float, lo: float = 0.0, hi: float = 1.0) -> float"

    def test_non_literal_default_becomes_ellipsis(self):
        obj = _NB((("def f(x: object = \\0) -> None", None, (object(),)),))
        assert nanobind_signatures(obj)[0].render() == "(x: object = ...) -> None"

    def test_overloads(self):
        obj = _NB((
            ("def __init__(self) -> None", None, None),
            ("def __init__(self, x: float, y: float = \\0) -> None", None, (0.0,)),
        ))
        sigs = nanobind_signatures(obj)
        assert [s.names for s in sigs] == [("self",), ("self", "x", "y")]

    def test_missing_attribute(self):
        assert nanobind_signatures(object()) == []

    def test_placeholder_out_of_range(self):
        obj = _NB((("def f(x: int = \\3)", None, ()),))
        assert nanobind_signatures(obj)[0].render() == "(x: int = ...)"


class TestFromInspect:
    def test_string_annotations_kept(self):
        ns: dict = {}
        src = 'def f(a: "int", *, b: "list[str]" = None) -> "float": ...'
        exec(compile(src, "<t>", "exec", dont_inherit=True), ns)
        sig = from_inspect(inspect.signature(ns["f"]))
        assert sig.render() == "(a: int, *, b: list[str] = None) -> float"

    def test_object_annotations_dropped(self):
        ns: dict = {}
        exec(compile("def g(a: int) -> int: ...", "<t>", "exec", dont_inherit=True), ns)
        assert from_inspect(inspect.signature(ns["g"])).render() == "(a)"


class _Builtinish:
    __name__ = "cross"
    __doc__ = "cross(a: Vec3, b: Vec3) -> Vec3\n\nCross product."
    __text_signature__ = None

    def __call__(self, *args, **kwargs): ...


class TestSignaturesOf:
    def test_docstring_preferred_over_generic_inspect(self):
        sigs = signatures_of(_Builtinish())
        assert len(sigs) == 1 and sigs[0].names == ("a", "b")

    def test_plain_python_function(self):
        def f(a, b=2, *rest, k, **kw): ...
        (sig,) = signatures_of(f)
        assert sig.names == ("a", "b", "rest", "k", "kw")

    def test_generic_only_returns_empty(self):
        def g(*args, **kwargs): ...
        assert signatures_of(g) == []

    @pytest.mark.skipif(sys.implementation.name != "cpython", reason="len is a C builtin only on CPython")
    def test_builtin_with_text_signature(self):
        (sig,) = signatures_of(len)
        assert len(sig.params) == 1
        assert sig.params[0].kind == POS_ONLY


class TestRender:
    def test_trailing_positional_only(self):
        sig = Signature((Param("a", POS_ONLY), Param("b", POS_ONLY)))
        assert sig.render() == "(a, b, /)"

    def test_varargs_suppresses_star(self):
        sig = Signature((Param("args", VAR_POS), Param("k", KW_ONLY, default="1")))
        assert sig.render() == "(*args, k=1)"

    def test_is_generic_ignores_self(self):
        sig = Signature((Param("self"), Param("args", VAR_POS), Param("kwargs", VAR_KW)))
        assert sig.is_generic()


class TestNormalizeType:
    @pytest.mark.parametrize(("raw", "c", "out"), [
        ("List[int]", False, "list[int]"),
        ("typing.Dict[str, int]", False, "dict[str, int]"),
        ("Optional[int]", False, "Optional[int]"),
        ("double", True, "float"),
        ("long long", True, "int"),
        ("MyExt", True, "MyExt"),
        ("not a type!", False, None),
        (None, False, None),
        ("", False, None),
    ])
    def test_cases(self, raw, c, out):
        assert normalize_type(raw, c_style=c) == out


class _InspectedWithDoc:
    """A C API / Cython ``binding=True`` callable: ``inspect`` sees the parameters, the doc names the return type."""

    def __init__(self, name: str, doc: str, sig: inspect.Signature) -> None:
        self.__name__ = name
        self.__doc__ = doc
        self.__signature__ = sig

    def __call__(self, *args, **kwargs): ...


_P = inspect.Parameter


class TestDocstringReturnType:
    def test_first_doc_line_gives_return_type(self):
        obj = _InspectedWithDoc("area", "area(points) -> float\n\nShoelace area.",
                                inspect.Signature([_P("points", POS_ONLY)]))
        (sig,) = signatures_of(obj)
        assert sig.render() == "(points, /) -> float"

    def test_generic_doc_line_return_type(self):
        obj = _InspectedWithDoc("f", "f(*args, **kwargs) -> int",
                                inspect.Signature([_P("a", POS_KW), _P("b", POS_KW, default=1)]))
        (sig,) = signatures_of(obj)
        assert sig.render() == "(a, b=1) -> int"

    def test_other_parameter_names_keep_doc_signature(self):
        obj = _InspectedWithDoc("f", "f(x, y) -> int", inspect.Signature([_P("a", POS_KW)]))
        (sig,) = signatures_of(obj)
        assert sig.render() == "(x, y) -> int"

    def test_typed_doc_line_wins(self):
        obj = _InspectedWithDoc("f", "f(double a) -> double", inspect.Signature([_P("a", POS_ONLY)]))
        (sig,) = signatures_of(obj)
        assert sig.render() == "(a: float) -> float"

    def test_no_doc_line_keeps_inspect(self):
        obj = _InspectedWithDoc("f", "Plain prose.", inspect.Signature([_P("a", POS_ONLY)]))
        (sig,) = signatures_of(obj)
        assert sig.render() == "(a, /)"
