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
import contextlib
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stubpy
from stubpy.core.pipeline import render_module
from stubpy.state.context import StubContext


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


def make_stub_ctx(source: str, **cfg) -> tuple[str, StubContext]:
    """Stub *source* with the Config fields in *cfg*; return the parsed-checked stub text and its context.

    The source goes to a fresh temporary folder as ``mod.py``, so it is a loose script.
    """
    from stubpy.config import Config

    folder = Path(tempfile.mkdtemp(prefix="stubpy_edge_"))
    src = folder / "mod.py"
    src.write_text(textwrap.dedent(source), encoding="utf-8")
    ctx = StubContext(config=Config(**cfg))
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
    from stubpy.state.context import StubContext
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
    from stubpy.state.context import StubContext
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


@contextlib.contextmanager
def on_sys_path(root: Path, package: str) -> Iterator[Path]:
    """Put *root* on ``sys.path`` for the block, then forget *package* and its submodules."""
    sys.path.insert(0, str(root))
    try:
        yield root
    finally:
        if str(root) in sys.path:
            sys.path.remove(str(root))
        for name in [m for m in sys.modules if m == package or m.startswith(package + ".")]:
            del sys.modules[name]


from tests.drawkit_sources import DRAWKIT  # noqa: E402

"""Sources of the ``drawkit`` test package: aliases, an ABC base and modules built on it."""


try:
    import pytest  # noqa: F401 — only needed for the decorator

    @pytest.fixture
    def empty_ctx() -> StubContext:
        """A fresh, empty StubContext."""
        return StubContext()

    @pytest.fixture(scope="session")
    def drawkit(tmp_path_factory) -> Iterator[Path]:
        """The importable ``drawkit`` package (see ``DRAWKIT``); yields its directory."""
        root = write_tree(tmp_path_factory.mktemp("drawkit_root"), DRAWKIT)
        with on_sys_path(root, "drawkit"):
            yield root / "drawkit"

    @pytest.fixture
    def drawkit_module(drawkit: Path, request):
        """Return a function that stubs *source* as a throwaway module inside ``drawkit``."""
        def render(source: str) -> str:
            name = "scratch_" + "".join(c if c.isalnum() else "_" for c in request.node.name)
            path = drawkit / f"{name}.py"
            path.write_text(textwrap.dedent(source), encoding="utf-8")
            try:
                return stubpy.render(str(path)).text
            finally:
                path.unlink(missing_ok=True)
                sys.modules.pop(f"drawkit.{name}", None)
        return render

    @pytest.fixture(scope="session")
    def element_stub(drawkit: Path) -> str:
        """Generated stub content for drawkit/element.py."""
        return stubpy.render(str(drawkit / "element.py")).text

    @pytest.fixture(scope="session")
    def container_stub(drawkit: Path) -> str:
        """Generated stub content for drawkit/container.py."""
        return stubpy.render(str(drawkit / "container.py")).text

    @pytest.fixture(scope="session")
    def graphics_stub(drawkit: Path) -> str:
        """Generated stub content for drawkit/graphics.py."""
        return stubpy.render(str(drawkit / "graphics.py")).text

    @pytest.fixture(scope="session")
    def functions_stub(drawkit: Path) -> str:
        """Generated stub content for drawkit/functions.py."""
        return stubpy.render(str(drawkit / "functions.py")).text

    @pytest.fixture(scope="session")
    def dispatch_stub(drawkit: Path) -> str:
        """Generated stub content for drawkit/dispatch.py."""
        return stubpy.render(str(drawkit / "dispatch.py")).text

    @pytest.fixture
    def ctx() -> StubContext:
        """A fresh StubContext for emitter/resolver tests."""
        return StubContext()

except ImportError:
    pass
