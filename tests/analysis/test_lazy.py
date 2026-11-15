"""Tests for stubpy.analysis.lazy: names a module ``__getattr__`` provides."""
import ast
import textwrap

from stubpy.analysis.lazy import static_lazy_exports


def _lazy(source: str):
    return static_lazy_exports(ast.parse(textwrap.dedent(source)))


def _imports(lazy) -> dict[str, tuple]:
    return {k: (v.module, v.name, v.asname) for k, v in lazy.imports.items()}


class TestStaticLazyExports:
    def test_no_getattr(self):
        assert _lazy("x = 1") is None

    def test_mapping_attribute_form(self):
        lazy = _lazy("""
            _LAZY = {"Canvas": ".core", "Pen": ("pkg.tools", "Pen"), "ink": "pkg.ink:make"}
            def __getattr__(name):
                if name in _LAZY:
                    return getattr(importlib.import_module(_LAZY[name], __name__), name)
                raise AttributeError(name)
        """)
        assert _imports(lazy) == {
            "Canvas": (".core", "Canvas", "Canvas"),
            "Pen": ("pkg.tools", "Pen", "Pen"),
            "ink": ("pkg.ink", "make", "ink"),
        }
        assert lazy.closed and lazy.names == {"Canvas", "Pen", "ink"}

    def test_mapping_module_form(self):
        lazy = _lazy("""
            def __getattr__(name):
                subs = {"io": ".io", "np": "numpy"}
                if name in subs:
                    return importlib.import_module(subs[name], __name__)
        """)
        assert _imports(lazy) == {"io": (".", "io", "io"), "np": (None, "numpy", "np")}
        assert not lazy.closed

    def test_if_chain(self):
        lazy = _lazy("""
            def __getattr__(name):
                if name == "Canvas":
                    from .core import Canvas
                    return Canvas
                elif name == "old":
                    from .core import new as _new
                    return _new
                elif name in ("a", "b"):
                    return getattr(importlib.import_module(".ab"), name)
                elif name == "sub":
                    return importlib.import_module(f"{__name__}.{name}")
                elif name == "VERSION":
                    return "1.0"
                elif name == "dynamic":
                    return compute()
                raise AttributeError(name)
        """)
        assert _imports(lazy) == {
            "Canvas": (".core", "Canvas", "Canvas"),
            "old": (".core", "new", "old"),
            "a": (".ab", "a", "a"),
            "b": (".ab", "b", "b"),
            "sub": (".", "sub", "sub"),
        }
        assert lazy.values == {"VERSION": "str"}
        assert "dynamic" in lazy.names and "dynamic" not in lazy.imports

    def test_relative_prefix_from_import_module_call(self):
        lazy = _lazy("""
            _LAZY = {"parse": ("io.parser", "parse")}
            def __getattr__(name):
                if name in _LAZY:
                    module_name, attribute = _LAZY[name]
                    return getattr(importlib.import_module(f".{module_name}", __name__), attribute)
                raise AttributeError(name)
        """)
        assert _imports(lazy) == {"parse": (".io.parser", "parse", "parse")}
