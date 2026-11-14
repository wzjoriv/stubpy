"""
tests/conftest.py
-----------------
Shared fixtures and utility functions used across the test suite.

Utility functions (``make_stub``, ``flatten``, ``assert_valid_syntax``) are
importable by test modules that run without pytest as well as by pytest
itself.  Pytest fixtures are defined at the bottom and silently unavailable
in non-pytest environments.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stubpy
from stubpy.core.context import StubContext
from stubpy.core.pipeline import render_module


def make_stub(source: str) -> str:
    """Write *source* to a temporary .py file, run the generator, return stub."""
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(source)
        tmp_path = Path(fh.name)
    return stubpy.render(str(tmp_path)).text


def flatten(content: str) -> str:
    """Collapse multi-line method signatures into a single line.

    Turns::

        def foo(
            self,
            x: int,
        ) -> None: ...

    Into::

        def foo(self, x: int,) -> None: ...
    """
    lines = content.splitlines()
    out: list[str] = []
    buf: list[str] = []
    for line in lines:
        if buf:
            stripped = line.strip()
            if stripped.startswith(")"):
                combined = buf[0] + ", ".join(buf[1:]) + stripped
                out.append(combined)
                buf = []
            else:
                buf.append(stripped)
        elif line.rstrip().endswith("("):
            buf.append(line.rstrip())
        else:
            out.append(line)
    out.extend(buf)
    return "\n".join(out)


def assert_valid_syntax(content: str) -> None:
    """Assert that *content* is parseable as valid Python."""
    try:
        ast.parse(content)
    except SyntaxError as exc:
        raise AssertionError(f"Generated stub has invalid syntax: {exc}") from exc


def make_stub_ctx(source: str, mode: str = "runtime", **cfg) -> tuple[str, StubContext]:
    """Stub *source* in execution *mode*; return the parsed-checked stub text and its context.

    The source goes to a fresh temporary folder as ``mod.py``, so it is a loose script.
    """
    from stubpy.config import Config, Mode

    folder = Path(tempfile.mkdtemp(prefix="stubpy_edge_"))
    src = folder / "mod.py"
    src.write_text(textwrap.dedent(source), encoding="utf-8")
    ctx = StubContext(config=Config(mode=Mode(mode), **cfg))
    stub = render_module(str(src), ctx)
    assert_valid_syntax(stub)
    return stub, ctx


def write_tree(root: Path, files: dict[str, str]) -> Path:
    """Write ``{relative_path: source}`` under *root* (dedented) and return *root*."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
    return root


def _ctx(**kwargs) -> "StubContext":
    """Return a fresh StubContext with optional Config overrides."""
    from stubpy.config import Config
    from stubpy.core.context import StubContext
    return StubContext(config=Config(**kwargs))


def _parse(stub: str) -> None:
    """Assert *stub* is syntactically valid Python."""
    import ast
    try:
        ast.parse(stub)
    except SyntaxError as exc:
        raise AssertionError(f"Stub has invalid syntax:\n{stub}") from exc


def _generate(src: str, **cfg_kwargs) -> str:
    """Compile *src*, generate a stub, return stub text."""
    import tempfile
    from pathlib import Path

    from stubpy.config import Config
    from stubpy.core.context import StubContext
    src = __import__("textwrap").dedent(src)
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as fh:
        fh.write(src)
        fname = fh.name
    try:
        ctx = StubContext(config=Config(**cfg_kwargs))
        return render_module(fname, ctx)
    finally:
        Path(fname).unlink(missing_ok=True)


import inspect as _inspect
import textwrap as _textwrap

_KW_ONLY    = _inspect.Parameter.KEYWORD_ONLY
_VAR_POS    = _inspect.Parameter.VAR_POSITIONAL
_VAR_KW     = _inspect.Parameter.VAR_KEYWORD
_POS_ONLY   = _inspect.Parameter.POSITIONAL_ONLY
_POS_KW     = _inspect.Parameter.POSITIONAL_OR_KEYWORD
_KW_SEP_NAME  = "__kw_sep__"
_POS_SEP_NAME = "__pos_sep__"


def _param(
    name: str,
    kind: "_inspect.Parameter" = None,
    annotation: object = _inspect.Parameter.empty,
    default: object = _inspect.Parameter.empty,
) -> "_inspect.Parameter":
    """Build an :class:`inspect.Parameter` for tests."""
    if kind is None:
        kind = _inspect.Parameter.POSITIONAL_OR_KEYWORD
    return _inspect.Parameter(name, kind, annotation=annotation, default=default)


def _compile_fn_from_source(src: str) -> dict:
    """Compile a source snippet and return the resulting namespace dict."""
    src = _textwrap.dedent(src)
    ns: dict = {}
    exec(compile(src, "<test>", "exec"), ns)  # noqa: S102
    return ns


def _harvest_fn(src: str, name: str):
    """Return ``(live_fn, ast_info, namespace)`` for *name* from *src*."""
    from stubpy.analysis.harvest import ast_harvest
    ns = _compile_fn_from_source(src)
    syms = ast_harvest(_textwrap.dedent(src))
    fi = next((f for f in syms.functions if f.name == name), None)
    return ns.get(name), fi, ns


def _param_names(result: list) -> list:
    """Extract parameter names from a resolve_* result list."""
    out = []
    for p, _ in result:
        if p.kind == _inspect.Parameter.VAR_POSITIONAL:
            out.append(f"*{p.name}")
        elif p.kind == _inspect.Parameter.VAR_KEYWORD:
            out.append(f"**{p.name}")
        else:
            out.append(p.name)
    return out


def _param_kinds(result: list) -> list:
    """Extract parameter kind names from a resolve_* result list."""
    kind_map = {
        _inspect.Parameter.POSITIONAL_ONLY:    "POS_ONLY",
        _inspect.Parameter.POSITIONAL_OR_KEYWORD: "POS_KW",
        _inspect.Parameter.VAR_POSITIONAL:     "VAR_POS",
        _inspect.Parameter.KEYWORD_ONLY:       "KW_ONLY",
        _inspect.Parameter.VAR_KEYWORD:        "VAR_KW",
    }
    return [kind_map[p.kind] for p, _ in result]


def assert_valid_python(stub: str) -> None:
    """Assert *stub* is parseable as valid Python (alias of assert_valid_syntax)."""
    assert_valid_syntax(stub)


try:
    import pytest  # noqa: F401 — only needed for the decorator

    @pytest.fixture
    def empty_ctx() -> StubContext:
        """A fresh, empty StubContext."""
        return StubContext()

    @pytest.fixture
    def demo_dir() -> Path:
        """Path to the demo/ package directory."""
        return ROOT / "demo"

    @pytest.fixture
    def element_stub(demo_dir: Path) -> str:
        """Generated stub content for demo/element.py."""
        return stubpy.render(str(demo_dir / "element.py")).text

    @pytest.fixture
    def container_stub(demo_dir: Path) -> str:
        """Generated stub content for demo/container.py."""
        return stubpy.render(str(demo_dir / "container.py")).text

    @pytest.fixture
    def graphics_stub(demo_dir: Path) -> str:
        """Generated stub content for demo/graphics.py."""
        return stubpy.render(str(demo_dir / "graphics.py")).text

    @pytest.fixture
    def ctx() -> StubContext:
        """A fresh StubContext for emitter/resolver tests."""
        return StubContext()

    @pytest.fixture
    def dispatch_stub(demo_dir: Path) -> str:
        """Generated stub content for demo/dispatch.py."""
        return stubpy.render(str(demo_dir / "dispatch.py")).text

except ImportError:
    pass
