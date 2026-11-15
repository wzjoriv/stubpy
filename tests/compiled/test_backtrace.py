"""``**kwargs`` / ``*args`` traced from Python code into compiled callables."""
from __future__ import annotations

import inspect
import textwrap

import stubpy
from stubpy.compiled.runtime import compiled_signature, compiled_signatures, overload_count
from stubpy.core.diagnostics import Level

from .fakes import FakeBuiltin, Widget

FAKES = textwrap.dedent('''
    class FakeBuiltin:
        def __init__(self, name, doc):
            self.__name__ = name
            self.__doc__ = doc

        def __call__(self, *args, **kwargs):
            return None
''')


def _render(tmp_path, source: str, name: str = "mod_bt") -> stubpy.StubResult:
    path = tmp_path / f"{name}.py"
    path.write_text(FAKES + textwrap.dedent(source), encoding="utf-8")
    return stubpy.render(path)


class TestRuntime:
    def test_single_signature(self):
        sig = compiled_signature(FakeBuiltin("f", "f(a: int, b: typing.SupportsFloat = 2.0) -> float"))
        assert isinstance(sig, inspect.Signature)
        assert [(p.name, p.annotation, p.default) for p in sig.parameters.values()] == [
            ("a", "int", inspect.Parameter.empty), ("b", "SupportsFloat", 2.0)]
        assert sig.return_annotation == "float"

    def test_annotations_needing_imports_are_dropped(self):
        sig = compiled_signature(FakeBuiltin("f", "f(a: numpy.ndarray, b: int) -> numpy.ndarray"))
        assert [p.annotation for p in sig.parameters.values()] == [inspect.Parameter.empty, "int"]
        assert sig.return_annotation is inspect.Signature.empty

    def test_overloads_give_no_single_signature(self):
        assert compiled_signature(Widget.__dict__["__init__"]) is None
        assert overload_count(Widget.__dict__["__init__"]) == 2

    def test_python_functions_are_not_compiled(self):
        def f(a): ...
        assert compiled_signatures(f) == [] and overload_count(f) == 0

    def test_slot_wrapper_constructor_uses_class_signature(self):
        sigs = compiled_signatures(type.__dict__["__init__"])
        assert all(s.params and s.params[0].name == "self" for s in sigs)


class TestSubclass:
    def test_constructor_kwargs_from_compiled_base(self, tmp_path):
        result = _render(tmp_path, '''
            class Base:
                __init__ = FakeBuiltin("__init__", "__init__(self: m.Base, width: int, height: int, samples: int = 4) -> None")

            class Child(Base):
                def __init__(self, width: int, *, rule: str = "nonzero", **kwargs):
                    super().__init__(width, 1, **kwargs)
        ''')
        assert "rule: str = 'nonzero'" in result.text
        assert "samples: int = 4" in result.text
        assert "**kwargs" not in result.text.split("class Child")[1]

    def test_args_and_kwargs_from_compiled_base(self, tmp_path):
        result = _render(tmp_path, '''
            class Base:
                __init__ = FakeBuiltin("__init__", "__init__(self, a: int, b: float = 1.0) -> None")

            class Child(Base):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
        ''', "mod_bt_args")
        child = result.text.split("class Child")[1]
        assert "a: int" in child and "b: float = 1.0" in child and "*args" not in child

    def test_overloaded_compiled_constructor_keeps_kwargs_with_info(self, tmp_path):
        result = _render(tmp_path, '''
            class Base:
                __init__ = FakeBuiltin("__init__", (
                    "__init__(*args, **kwargs)\\nOverloaded function.\\n\\n"
                    "1. __init__(self: m.Base) -> None\\n\\n"
                    "2. __init__(self: m.Base, size: int) -> None\\n"
                ))

            class Child(Base):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
        ''', "mod_bt_over")
        assert "def __init__(self, *args, **kwargs) -> None: ..." in result.text
        notes = [d for d in result.diagnostics if d.level is Level.INFO and "2 overloads" in d.message]
        assert notes and notes[0].symbol == "Child.__init__"


class TestFunctions:
    def test_function_forwarding_into_compiled_function(self, tmp_path):
        result = _render(tmp_path, '''
            gaussian = FakeBuiltin("gaussian", "gaussian(img: object, std: float, truncate: float = 4.0) -> object")

            def blur(img, std: float, **kwargs):
                return gaussian(img, std, **kwargs)
        ''', "mod_bt_fn")
        blur = result.text.split("def blur")[1]
        assert "truncate: float = 4.0" in blur and "**kwargs" not in blur

    def test_forwarding_into_overloaded_compiled_function(self, tmp_path):
        result = _render(tmp_path, '''
            flood = FakeBuiltin("flood", (
                "flood(*args, **kwargs)\\nOverloaded function.\\n\\n"
                "1. flood(h: int, w: int) -> None\\n\\n"
                "2. flood(like: object) -> None\\n"
            ))

            def fill(*args, **kwargs):
                return flood(*args, **kwargs)
        ''', "mod_bt_fn_over")
        assert "def fill(*args, **kwargs)" in result.text
        assert any("flood is compiled with 2 overloads" in d.message for d in result.diagnostics)


def test_numba_style_dispatcher_is_a_plain_def(tmp_path):
    path = tmp_path / "mod_jit.py"
    path.write_text(textwrap.dedent('''
        class Dispatcher:
            def __init__(self, fn):
                self.py_func = fn
                self.__name__ = fn.__name__
                self.__doc__ = fn.__doc__

            def __call__(self, *args):
                return self.py_func(*args)

        def _kernel(x: float, n: int = 2) -> float:
            return x * n

        kernel = Dispatcher(_kernel)

        def scale(x: float, n: int = 2) -> float:
            return x * n

        scale = Dispatcher(scale)
    '''), encoding="utf-8")
    text = stubpy.render(path).text
    assert "def scale(x: float, n: int = 2) -> float: ..." in text
