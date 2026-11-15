"""``*args`` / ``**kwargs`` forwarded through function-local imports and nested calls are traced to the callee."""
import ast

import pytest

import stubpy
from stubpy import Config

SHAPES = '''
class Circle:
    def __init__(self, cx: float = 0, cy: float = 0, r: float = 1, *, fill: str = "none") -> None: ...
'''

FACTORY = '''
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from .shapes import Circle

class ElementFactory:
    def _place(self, el): return el
    def circle(self, *args: Any, **kwargs: Any) -> "Circle":
        from .shapes import Circle
        return self._place(Circle(*args, **kwargs))
    def circle_abs(self, *args: Any, **kwargs: Any) -> "Circle":
        from {pkg}.shapes import Circle
        return self._place(Circle(*args, **kwargs))
    def circle_cond(self, flag, *args: Any, **kwargs: Any):
        from .shapes import Circle
        return [self._place(Circle(*args, **kwargs)) if flag else None]
    def circle_dict(self, *args: Any, **kwargs: Any):
        from .shapes import Circle
        return {{"k": [Circle(*args, **kwargs)]}}
    def circle_with(self, *args: Any, **kwargs: Any):
        from .shapes import Circle
        with self._ctx(Circle(*args, **kwargs)) as c:
            return c
    async def circle_await(self, *args: Any, **kwargs: Any):
        from .shapes import Circle
        return await self._place(Circle(*args, **kwargs))
    def circle_lambda(self, *args: Any, **kwargs: Any):
        from .shapes import Circle
        return lambda: Circle(*args, **kwargs)
    @classmethod
    def make(cls, name, *args: Any, **kwargs: Any):
        return cls._registry[name](*args, **kwargs)
'''

EXPANDED = ["circle", "circle_abs", "circle_cond", "circle_dict", "circle_with", "circle_await"]


def _methods(stub: str) -> dict[str, str]:
    cls = next(n for n in ast.parse(stub).body if isinstance(n, ast.ClassDef) and n.name == "ElementFactory")
    return {
        n.name: ast.unparse(n.args)
        for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


@pytest.fixture(params=["runtime", "ast"])
def generated(request, tmp_path):
    """Generate the factory module in the requested mode; return ``(mode, signatures)``."""
    name = "lf_" + "".join(c for c in tmp_path.name if c.isalnum()) + request.param
    pkg = tmp_path / "src" / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "shapes.py").write_text(SHAPES)
    (pkg / "factory.py").write_text(FACTORY.format(pkg=name))
    out = tmp_path / "out"
    stubpy.generate(str(pkg / "factory.py"), str(out / "factory.pyi"), config=Config(mode=request.param))
    stub = next(out.rglob("factory.pyi")).read_text(encoding="utf-8")
    return request.param, _methods(stub)


@pytest.mark.parametrize("name", EXPANDED)
def test_forwarding_call_is_expanded(generated, name):
    sig = generated[1][name]
    assert "cx: float=0" in sig and "fill: str='none'" in sig, sig
    assert "args" not in sig


def test_nested_scope_is_not_scanned(generated):
    assert "**kwargs" in generated[1]["circle_lambda"]


def test_registry_lookup_stays_unresolved(generated):
    assert "*args: Any, **kwargs: Any" in generated[1]["make"]


def test_registry_lookup_reports_info(tmp_path):
    pkg = tmp_path / "lfreg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "m.py").write_text(FACTORY.format(pkg="lfreg"))
    (pkg / "shapes.py").write_text(SHAPES)
    report = stubpy.generate(str(pkg / "m.py"), str(tmp_path / "o" / "m.pyi"), config=Config(mode="runtime"))
    diags = [d for r in report.results for d in r.diagnostics if d.symbol == "ElementFactory.make"]
    assert any("cannot be resolved statically" in d.message for d in diags)
