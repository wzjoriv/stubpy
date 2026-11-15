"""Tests for stubpy.analysis.docstrings."""
from __future__ import annotations

from stubpy.analysis.docstrings import DocstringTypes, parse_docstring_types
from stubpy.analysis.docstrings._clean import clean_type
from stubpy.analysis.docstrings._google import parse_google
from stubpy.analysis.docstrings._numpy import parse_numpy
from stubpy.analysis.docstrings._sphinx import parse_sphinx


class TestCleanType:
    def test_strips_whitespace(self):
        assert clean_type("  int  ") == "int"

    def test_empty_returns_empty(self):
        assert clean_type("") == ""
        assert clean_type("   ") == ""

    def test_or_normalisation(self):
        assert clean_type("int or None") == "int | None"
        assert clean_type("str or int or float") == "str | int | float"

    def test_optional_stripped(self):
        assert clean_type("int, optional") == "int"
        assert clean_type("str,optional") == "str"
        assert clean_type("list[str], optional") == "list[str]"

    def test_generics_preserved(self):
        assert clean_type("list[str]") == "list[str]"
        assert clean_type("dict[str, int]") == "dict[str, int]"

    def test_description_words_rejected(self):
        assert clean_type("a list of strings") == ""
        assert clean_type("the value") == ""
        assert clean_type("an optional flag") == ""

    def test_long_descriptions_rejected(self):
        assert clean_type("one two three four five") == ""

    def test_complex_type_passes(self):
        assert clean_type("list[str] | None") == "list[str] | None"

    def test_none_type(self):
        assert clean_type("None") == "None"

    def test_or_with_spaces(self):
        assert clean_type("int  or  None") == "int | None"


class TestParseNumpy:
    def test_basic_params(self):
        doc = """
Summary line.

Parameters
----------
x : int
    Description of x.
y : str
    Description of y.
"""
        r = parse_numpy(doc)
        assert r.params == {"x": "int", "y": "str"}

    def test_optional_param(self):
        doc = """
Parameters
----------
alpha : float, optional
    Opacity value.
"""
        r = parse_numpy(doc)
        assert r.params == {"alpha": "float"}

    def test_returns_simple(self):
        doc = """
Returns
-------
float
    The computed value.
"""
        r = parse_numpy(doc)
        assert r.returns == "float"

    def test_returns_name_colon_type(self):
        doc = """
Returns
-------
result : bool
    Whether it succeeded.
"""
        r = parse_numpy(doc)
        assert r.returns == "bool"

    def test_generic_type(self):
        doc = """
Parameters
----------
items : list[str]
    The items.
"""
        r = parse_numpy(doc)
        assert r.params == {"items": "list[str]"}

    def test_or_union(self):
        doc = """
Parameters
----------
value : int or None
    The value.
"""
        r = parse_numpy(doc)
        assert r.params == {"value": "int | None"}

    def test_empty_returns_empty(self):
        assert parse_numpy("").is_empty()
        assert parse_numpy("Just a plain description.").is_empty()

    def test_multiple_sections(self):
        doc = """
Summary.

Parameters
----------
x : int
    desc

Other Parameters
----------------
y : float
    desc
"""
        r = parse_numpy(doc)
        assert "x" in r.params
        assert "y" in r.params


class TestParseGoogle:
    def test_basic_args(self):
        doc = """Summary.

Args:
    x (int): Description of x.
    y (str): Description of y.
"""
        r = parse_google(doc)
        assert r.params == {"x": "int", "y": "str"}

    def test_optional_arg(self):
        doc = """Summary.

Args:
    z (float, optional): An optional float.
"""
        r = parse_google(doc)
        assert r.params == {"z": "float"}

    def test_returns(self):
        doc = """Summary.

Returns:
    bool: Whether it worked.
"""
        r = parse_google(doc)
        assert r.returns == "bool"

    def test_keyword_args_section(self):
        doc = """Summary.

Keyword Args:
    dpi (int): Resolution.
"""
        r = parse_google(doc)
        assert r.params == {"dpi": "int"}

    def test_generic_type(self):
        doc = """Summary.

Args:
    items (list[str]): A list.
"""
        r = parse_google(doc)
        assert r.params == {"items": "list[str]"}

    def test_empty(self):
        assert parse_google("").is_empty()

    def test_parameters_section_alias(self):
        doc = """Summary.

Parameters:
    x (int): Description.
"""
        r = parse_google(doc)
        assert r.params.get("x") == "int"


class TestParseSphinx:
    def test_combined_param(self):
        doc = ":param int x: Description of x."
        r = parse_sphinx(doc)
        assert r.params == {"x": "int"}

    def test_name_and_type_directives(self):
        doc = ":param x: Description.\n:type x: str"
        r = parse_sphinx(doc)
        assert r.params == {"x": "str"}

    def test_type_overrides_combined(self):
        doc = ":param float x: desc.\n:type x: int"
        r = parse_sphinx(doc)
        assert r.params["x"] == "int"

    def test_rtype(self):
        doc = ":rtype: float"
        r = parse_sphinx(doc)
        assert r.returns == "float"

    def test_empty(self):
        assert parse_sphinx("").is_empty()

    def test_multiple_params(self):
        doc = ":param int x: desc\n:param str y: desc\n:rtype: bool"
        r = parse_sphinx(doc)
        assert r.params == {"x": "int", "y": "str"}
        assert r.returns == "bool"

    def test_name_only_without_type_excluded(self):
        doc = ":param x: some description"
        r = parse_sphinx(doc)
        assert "x" not in r.params


class TestDocstringTypesMerge:
    def test_self_wins(self):
        a = DocstringTypes(params={"x": "int"}, returns="float")
        b = DocstringTypes(params={"x": "str"}, returns="bool")
        m = a.merge(b)
        assert m.params["x"] == "int"
        assert m.returns == "float"

    def test_other_fills_gaps(self):
        a = DocstringTypes(params={"x": "int"}, returns=None)
        b = DocstringTypes(params={"y": "str"}, returns="float")
        m = a.merge(b)
        assert m.params == {"x": "int", "y": "str"}
        assert m.returns == "float"

    def test_both_empty(self):
        m = DocstringTypes().merge(DocstringTypes())
        assert m.is_empty()

    def test_is_empty(self):
        assert DocstringTypes().is_empty()
        assert not DocstringTypes(params={"x": "int"}).is_empty()
        assert not DocstringTypes(returns="str").is_empty()


class TestParseDocstringTypes:
    def test_none_input(self):
        assert parse_docstring_types(None).is_empty()

    def test_empty_string(self):
        assert parse_docstring_types("").is_empty()

    def test_numpy_style(self):
        doc = "Parameters\n----------\nx : int\n    desc\n\nReturns\n-------\nbool\n    result"
        r = parse_docstring_types(doc)
        assert r.params.get("x") == "int"
        assert r.returns == "bool"

    def test_google_style(self):
        doc = "Args:\n    x (int): desc\n    y (str): desc\nReturns:\n    float: value"
        r = parse_docstring_types(doc)
        assert r.params == {"x": "int", "y": "str"}
        assert r.returns == "float"

    def test_sphinx_style(self):
        doc = ":param int x: desc\n:type y: str\n:rtype: float"
        r = parse_docstring_types(doc)
        assert r.params.get("x") == "int"
        assert r.params.get("y") == "str"
        assert r.returns == "float"

    def test_mixed_styles_merged(self):
        doc = "Args:\n    x (int): desc\nReturns:\n    float: value\n:rtype: bool"
        r = parse_docstring_types(doc)
        assert r.params.get("x") == "int"
        assert r.returns in ("float", "bool")

    def test_no_types_in_doc(self):
        r = parse_docstring_types("Just a plain description with no type info.")
        assert r.is_empty()


class TestDocstringInferenceInStubs:
    def test_unannotated_function_gets_type_comment(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text('''\
def compute(x, y, z=None):
    """
    Args:
        x (int): First value.
        y (float): Second value.
        z (str, optional): Optional string.
    Returns:
        bool: Result.
    """
    return True
''')
        from stubpy import generate_stub
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        ctx = StubContext(config=StubConfig(infer_types_from_docstrings=True))
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "# type: int" in stub
        assert "# type: float" in stub
        assert "# type: str" in stub

    def test_annotated_params_not_overridden(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text('''\
def compute(x: int, y: float) -> bool:
    """
    Args:
        x (str): Wrong type in docstring.
        y (list): Wrong type in docstring.
    Returns:
        int: Wrong return type.
    """
    return True
''')
        from stubpy import generate_stub
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        ctx = StubContext(config=StubConfig(infer_types_from_docstrings=True))
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "x: int" in stub
        assert "y: float" in stub
        assert "-> bool" in stub
        assert "# type:" not in stub

    def test_disabled_by_default(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text('''\
def compute(x, y):
    """
    Args:
        x (int): desc
    """
    return True
''')
        from stubpy import generate_stub
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        ctx = StubContext(config=StubConfig())
        stub = generate_stub(str(src), str(tmp_path / "mod.pyi"), ctx=ctx)
        assert "# type:" not in stub
