"""Tests for infer_type_from_literal."""
from __future__ import annotations


class TestInferTypeFromLiteral:
    """Unit tests for :func:`~stubpy.analysis.harvest.infer_type_from_literal`."""

    def _infer(self, expr: str):
        import ast

        from stubpy.analysis.harvest import infer_type_from_literal
        return infer_type_from_literal(ast.parse(expr, mode="eval").body)

    def test_int(self):       assert self._infer("42")    == "int"
    def test_float(self):     assert self._infer("3.14")  == "float"
    def test_str(self):       assert self._infer('"hi"')  == "str"
    def test_bool_true(self): assert self._infer("True")  == "bool"
    def test_bool_false(self):assert self._infer("False") == "bool"
    def test_none(self):      assert self._infer("None")  == "None"
    def test_bytes(self):     assert self._infer("b'x'")  == "bytes"
    def test_negative_int(self):   assert self._infer("-42")   == "int"
    def test_negative_float(self): assert self._infer("-3.14") == "float"

    def test_bool_before_int(self):
        """bool must return 'bool', not 'int' (bool is a subtype of int)."""
        assert self._infer("True") == "bool"
        assert self._infer("False") == "bool"

    def test_homogeneous_list(self):
        assert self._infer("[1, 2, 3]") == "list[int]"
        assert self._infer('["a", "b"]') == "list[str]"

    def test_empty_list(self):      assert self._infer("[]") == "list"
    def test_heterogeneous_list(self): assert self._infer("[1, 'x']") == "list"

    def test_homogeneous_tuple(self):
        assert self._infer("(1, 2)") == "tuple[int, int]"
        assert self._infer('(1, "x")') == "tuple[int, str]"

    def test_empty_tuple(self):    assert self._infer("()") == "tuple[()]"

    def test_homogeneous_set(self):
        assert self._infer("{1, 2}") == "set[int]"

    def test_typed_dict(self):
        assert self._infer('{"a": 1}') == "dict[str, int]"

    def test_empty_dict(self):      assert self._infer("{}") == "dict"
    def test_heterogeneous_dict(self): assert self._infer('{"a": 1, "b": "x"}') == "dict"

    def test_variable_returns_none(self):
        assert self._infer("some_var") is None

    def test_function_call_returns_none(self):
        assert self._infer("int()") is None

    def test_complex_literal(self):
        assert self._infer("2j") == "complex"

    def test_unary_minus_int(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("-42", mode="eval").body
        assert infer_type_from_literal(node) == "int"

    def test_unary_minus_float(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("-3.14", mode="eval").body
        assert infer_type_from_literal(node) == "float"

    def test_complex_via_binop(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("1+2j", mode="eval").body
        assert infer_type_from_literal(node) == "complex"

    def test_complex_pure_imaginary(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("2j", mode="eval").body
        assert infer_type_from_literal(node) == "complex"

    def test_ellipsis_yields_any(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("...", mode="eval").body
        assert infer_type_from_literal(node) == "Any"

    def test_empty_tuple_direct_call(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("()", mode="eval").body
        result = infer_type_from_literal(node)
        assert result in ("tuple[()]", "tuple")

    def test_variable_reference_returns_none(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("os.sep", mode="eval").body
        assert infer_type_from_literal(node) is None

    def test_constructor_call_returns_none(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("list()", mode="eval").body
        assert infer_type_from_literal(node) is None

    def test_heterogeneous_list_returns_bare_list(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse("[1, 'a', True]", mode="eval").body
        assert infer_type_from_literal(node) == "list"

    def test_heterogeneous_dict_returns_bare_dict(self):
        import ast as _ast

        from stubpy.analysis.harvest import infer_type_from_literal
        node = _ast.parse('{"a": 1, "b": "x"}', mode="eval").body
        assert infer_type_from_literal(node) == "dict"
