"""End-to-end **kwargs / *args backtracing."""
from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path

from stubpy import generate_stub
from tests.conftest import assert_valid_syntax, flatten, make_stub


class TestPlain:
    def test_basic_signature(self):
        c = make_stub("""
            class Rect:
                def __init__(self, width: float, height: float) -> None: pass
                def area(self) -> float: return self.width * self.height
        """)
        assert "def __init__(self, width: float, height: float) -> None:" in c
        assert "def area(self) -> float:" in c

    def test_default_value(self):
        c = make_stub("class Box:\n    def __init__(self, size: int = 10) -> None: pass\n")
        assert "size: int = 10" in c

    def test_no_hints_keeps_param_names(self):
        c = make_stub("class Bare:\n    def __init__(self, x, y): pass\n")
        assert "def __init__(self, x, y)" in c


class TestAnnotations:
    def test_optional_shorthand(self):
        c = make_stub("""
            class A:
                def __init__(self, x: str | None = None) -> None: pass
        """)
        assert "str | None" in c

    def test_union_three_types(self):
        c = make_stub("""
            class A:
                def __init__(self, x: str | int | float) -> None: pass
        """)
        assert "str | int | float" in c

    def test_callable_annotation(self):
        c = make_stub("""
            from typing import Callable
            class A:
                def __init__(self, fn: Callable[[], None] | None = None) -> None: pass
        """)
        assert "Callable" in c

    def test_literal_annotation(self):
        c = make_stub("""
            from typing import Literal
            class A:
                def __init__(self, cap: Literal["butt", "round"] = "butt") -> None: pass
        """)
        assert "Literal['butt', 'round']" in c

    def test_tuple_annotation(self):
        c = make_stub("""
            from typing import Tuple
            class A:
                def __init__(self, pt: Tuple[float, float]) -> None: pass
        """)
        assert "Tuple[float, float]" in c


class TestSingleKwargs:
    SRC = """
        class Parent:
            def __init__(self, color: str, size: int) -> None: pass
        class Child(Parent):
            def __init__(self, label: str, **kwargs): super().__init__(**kwargs)
    """

    @staticmethod
    def _child_section(c: str) -> str:
        return c.split("class Child")[1].split("\nclass ")[0]

    def test_merged(self):
        c = make_stub(self.SRC)
        child = self._child_section(c)
        assert "label: str" in child
        assert "color: str" in child
        assert "size: int"  in child

    def test_kwargs_gone(self):
        c = make_stub(self.SRC)
        assert "**kwargs" not in self._child_section(c)

    def test_defaults_preserved(self):
        c = make_stub("""
            class B:
                def __init__(self, x: float = 0.0) -> None: pass
            class D(B):
                def __init__(self, name: str, **kwargs): super().__init__(**kwargs)
        """)
        assert "x: float = 0.0" in c


class TestMultiLevel:
    SRC = """
        class A:
            def __init__(self, name: str, legs: int, wild: bool = True) -> None: pass
        class B(A):
            def __init__(self, owner: str, **kwargs): super().__init__(**kwargs)
        class C(B):
            def __init__(self, breed: str, **kwargs): super().__init__(**kwargs)
        class D(C):
            def __init__(self, job: str, **kwargs): super().__init__(**kwargs)
    """

    @staticmethod
    def _sec(c: str, name: str) -> str:
        return c.split(f"class {name}")[1].split("\nclass ")[0]

    def test_three_levels(self):
        c = make_stub(self.SRC)
        s = self._sec(c, "C")
        for p in ("breed: str", "owner: str", "name: str", "legs: int"):
            assert p in s
        assert "**kwargs" not in s

    def test_four_levels_with_default(self):
        c = make_stub(self.SRC)
        s = self._sec(c, "D")
        for p in ("job: str", "breed: str", "owner: str", "name: str", "wild: bool = True"):
            assert p in s
        assert "**kwargs" not in s

    def test_own_param_comes_first(self):
        s = flatten(self._sec(make_stub(self.SRC), "C"))
        init = next(line for line in s.splitlines() if "def __init__" in line)
        assert init.index("breed") < init.index("owner") < init.index("name")


class TestEdgeCases:
    def test_open_kwargs_preserved_when_no_parent(self):
        c = make_stub("class W:\n    def __init__(self, x: str, **kwargs): pass\n")
        assert "**kwargs" in c

    def test_unresolved_args_preserved(self):
        c = make_stub("class V:\n    def __init__(self, first: int, *args): pass\n")
        assert "*args" in c

    def test_kw_only_gets_separator(self):
        c = flatten(make_stub("""
            class K:
                def __init__(self, a: int, *, b: str = "x") -> None: pass
        """))
        init_line = [l for l in c.splitlines() if "def __init__" in l][0]
        assert "*," in init_line
        assert init_line.index("*,") < init_line.index("b:")


class TestSpecialMethods:
    def test_classmethod(self):
        c = make_stub("""
            class F:
                @classmethod
                def create(cls, v: int) -> 'F': return cls()
        """)
        assert "@classmethod" in c
        assert "def create(cls, v: int)" in c

    def test_staticmethod(self):
        c = make_stub("""
            class U:
                @staticmethod
                def add(a: int, b: int) -> int: return a + b
        """)
        assert "@staticmethod" in c
        assert "def add(a: int, b: int) -> int:" in c

    def test_property_with_setter(self):
        c = make_stub("""
            class P:
                @property
                def value(self) -> float: return self._v
                @value.setter
                def value(self, v: float) -> None: self._v = v
        """)
        assert "@property"     in c
        assert "def value(self) -> float:" in c
        assert "@value.setter" in c
        assert "def value(self, v: float) -> None:" in c


class TestClassmethodCls:
    SRC = """
        class Widget:
            def __init__(self, width: int, height: int, color: str = "black") -> None:
                pass

            @classmethod
            def square(cls, **kwargs) -> 'Widget':
                return cls(**kwargs)

            @classmethod
            def colored(cls, color: str, **kwargs) -> 'Widget':
                return cls(color=color, **kwargs)
    """

    @staticmethod
    def _method_line(content: str, method: str) -> str:
        for line in flatten(content).splitlines():
            if f"def {method}(cls" in line:
                return line
        return ""

    def test_square_gets_init_params(self):
        c = make_stub(self.SRC)
        line = self._method_line(c, "square")
        assert line, "square method not found"
        assert "width: int"  in line
        assert "height: int" in line
        assert "color: str"  in line
        assert "**kwargs"    not in line

    def test_colored_excludes_explicit_param_once(self):
        c = make_stub(self.SRC)
        line = self._method_line(c, "colored")
        assert line, "colored method not found"
        assert "color: str" in line
        assert "width: int" in line
        assert line.count("color:") == 1

    def test_chained_cls_kwargs(self):
        c = make_stub("""
            class Base:
                def __init__(self, x: int, y: int) -> None: pass
            class Child(Base):
                def __init__(self, label: str, **kwargs): super().__init__(**kwargs)
                @classmethod
                def make(cls, **kwargs) -> 'Child':
                    return cls(**kwargs)
        """)
        line = self._method_line(c, "make")
        assert "label: str" in line
        assert "x: int"     in line
        assert "y: int"     in line
        assert "**kwargs"   not in line


class TestTypeAliasPreservation:
    @staticmethod
    def _make_types_package() -> tuple[str, str]:
        tmpdir = tempfile.mkdtemp()
        types_src = textwrap.dedent("""
            from typing import Literal, Tuple
            Number = int | float
            Length = str | float | int
            Color  = str | Tuple[float, float, float]
            Cap    = Literal["butt", "round", "square"]
        """)
        open(os.path.join(tmpdir, "__init__.py"), "w").close()
        open(os.path.join(tmpdir, "types.py"), "w").write(types_src)
        return tmpdir, os.path.basename(tmpdir)

    def test_aliases_preserved_not_expanded(self):
        tmpdir, pkg_name = self._make_types_package()
        src = textwrap.dedent(f"""
            from __future__ import annotations
            import sys
            sys.path.insert(0, {repr(os.path.dirname(tmpdir))})
            from {pkg_name} import types

            class Shape:
                def __init__(self, width: types.Length, color: types.Color) -> None:
                    pass
        """)
        tmp = tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8", dir=tmpdir
        )
        tmp.write(src); tmp.flush(); tmp.close()
        c = generate_stub(tmp.name, str(Path(tmp.name).with_suffix(".pyi")))
        assert "types.Length" in c
        assert "types.Color"  in c
        assert "str | float | int" not in c

    def test_type_module_import_in_header(self):
        tmpdir, pkg_name = self._make_types_package()
        src = textwrap.dedent(f"""
            from __future__ import annotations
            import sys
            sys.path.insert(0, {repr(os.path.dirname(tmpdir))})
            from {pkg_name} import types

            class A:
                def __init__(self, x: types.Length) -> None: pass
        """)
        tmp = tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8", dir=tmpdir
        )
        tmp.write(src); tmp.flush(); tmp.close()
        c = generate_stub(tmp.name, str(Path(tmp.name).with_suffix(".pyi")))
        header = "\n".join(c.splitlines()[:10])
        assert "import types" in header


class TestFormatting:
    def test_many_params_multiline(self):
        c = make_stub("""
            class A:
                def __init__(self, x: int, y: int, z: int) -> None: pass
        """)
        def_lines = [l for l in c.splitlines() if "def __init__" in l]
        assert def_lines
        assert def_lines[0].rstrip().endswith("("), \
            "Expected multi-line: def line should end with '('"

    def test_few_params_inline(self):
        c = make_stub("""
            class A:
                def move(self, x: int, y: int) -> None: pass
        """)
        move_lines = [l for l in c.splitlines() if "def move" in l]
        assert move_lines
        assert "x: int" in move_lines[0], "Expected inline formatting"

    def test_multiline_is_valid_python(self):
        c = make_stub("""
            class A:
                def __init__(self, a: int, b: str, c: float, d: bool = True) -> None: pass
        """)
        assert_valid_syntax(c)

    def test_trailing_comma_on_param_lines(self):
        c = make_stub("""
            class A:
                def __init__(self, x: int, y: int, z: int) -> None: pass
        """)
        for line in c.splitlines():
            stripped = line.strip()
            if any(p in stripped for p in ("x:", "y:", "z:")) and ")" not in stripped:
                assert stripped.endswith(","), f"Missing trailing comma: {line!r}"


class TestStaticMethods:
    def test_static_no_args(self):
        c = make_stub("""
            class A:
                @staticmethod
                def util() -> int: return 42
        """)
        assert "@staticmethod" in c
        assert "def util() -> int: ..." in c
        assert "self" not in c.split("def util")[1].split("\n")[0]
        assert "cls"  not in c.split("def util")[1].split("\n")[0]

    def test_static_with_args(self):
        c = make_stub("""
            class A:
                @staticmethod
                def add(a: float, b: float = 1.0) -> float: return a + b
        """)
        assert "def add(a: float, b: float = 1.0) -> float: ..." in c

    def test_static_open_kwargs(self):
        c = make_stub("""
            class A:
                @staticmethod
                def factory(**kwargs) -> None: pass
        """)
        assert "@staticmethod" in c
        assert "**kwargs" in c

    def test_static_not_inherited_by_stub(self):
        """Only methods defined directly on the class appear."""
        c = make_stub("""
            class Parent:
                @staticmethod
                def parent_util() -> int: return 0
            class Child(Parent):
                @staticmethod
                def child_util() -> str: return ""
        """)
        child_sec = c.split("class Child")[1]
        assert "child_util" in child_sec
        assert "parent_util" not in child_sec

    def test_static_valid_syntax(self):
        c = make_stub("""
            class A:
                @staticmethod
                def compute(x: int, y: int, z: int) -> int: return x + y + z
        """)
        assert_valid_syntax(c)


class TestArgsAndKwargsTogether:
    def test_both_no_parent(self):
        """*args and **kwargs together with no parent are both preserved."""
        c = make_stub("""
            from typing import Any
            class A:
                def __init__(self, x: int, *args: str, flag: bool = False, **kwargs: Any) -> None:
                    pass
        """)
        c_flat = flatten(c)
        init = [l for l in c_flat.splitlines() if "def __init__" in l][0]
        assert "*args: str"     in init
        assert "**kwargs: Any"  in init
        assert "flag: bool"     in init
        assert init.index("*args") < init.index("**kwargs")
        assert_valid_syntax(c)

    def test_args_before_kwargs_in_output(self):
        """*args always appears before **kwargs in the emitted signature."""
        c = make_stub("""
            class Parent:
                def __init__(self, label: str, **kwargs) -> None: pass
            class Child(Parent):
                def __init__(self, *items: int, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "*items: int" in init_line
        assert "**kwargs"    in init_line
        assert init_line.index("*items") < init_line.index("**kwargs")
        assert_valid_syntax(c)

    def test_args_before_kwargs_open_parent(self):
        """*args precedes residual **kwargs when parent **kwargs is unresolved."""
        c = make_stub("""
            class Parent:
                def __init__(self, label: str, **kwargs) -> None: pass
            class Child(Parent):
                def __init__(self, *items: int, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "label: str"  in init_line
        assert "*items: int" in init_line
        assert "**kwargs"    in init_line
        assert init_line.index("*items") < init_line.index("**kwargs")
        assert_valid_syntax(c)

    def test_args_after_resolved_kwargs_params(self):
        """When **kwargs resolves fully, *args follows the concrete params."""
        c = make_stub("""
            class Parent:
                def __init__(self, color: str = "black", size: int = 10) -> None: pass
            class Child(Parent):
                def __init__(self, *args: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "color: str"  in init_line
        assert "size: int"   in init_line
        assert "*args: str"  in init_line
        assert "**kwargs" not in init_line
        assert init_line.index("color") < init_line.index("*args")
        assert_valid_syntax(c)

    def test_three_level_with_star_args(self):
        """Three-level chain where grandchild has *args."""
        c = make_stub("""
            class GrandParent:
                def __init__(self, width: float, height: float) -> None: pass
            class Middle(GrandParent):
                def __init__(self, name: str, **kwargs) -> None:
                    super().__init__(**kwargs)
            class GrandChild(Middle):
                def __init__(self, *tags: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        gc_sec = flatten(c.split("class GrandChild")[1])
        init_line = [l for l in gc_sec.splitlines() if "def __init__" in l][0]
        assert "name: str"   in init_line
        assert "width: float" in init_line
        assert "*tags: str"  in init_line
        assert "**kwargs" not in init_line
        assert_valid_syntax(c)

    def test_kw_only_with_kwargs_resolved(self):
        """Keyword-only params from parent survive through **kwargs backtracing."""
        c = make_stub("""
            class Parent:
                def __init__(self, a: int, *, b: str = "x") -> None: pass
            class Child(Parent):
                def __init__(self, prefix: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "prefix: str" in init_line
        assert "a: int"      in init_line
        assert "b: str"      in init_line
        assert "*,"          in init_line
        assert "**kwargs" not in init_line
        assert_valid_syntax(c)
