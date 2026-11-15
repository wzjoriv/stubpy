"""Copy docstrings from compiled (Cython) modules into their hand-maintained ``.pyi`` stubs, so IDEs show the
docs ``help()`` shows at the REPL.

The ``.pyx`` stays the one source of docstring *content*; this only keeps each stub in step with it. The
stubs are found, not listed: every ``*.pyx`` under the configured packages with a ``.pyi`` of the same stem
next to it (``pkg/_base.pyx`` -> ``pkg/_base.pyi``, module ``pkg._base``). ``overrides`` maps a module to a
stub of another name or place (and an empty string drops a discovered one)::

    [tool.devkit.pyi]
    packages = ["mypkg"]                  # folders searched for *.pyx (relative to the repository root)
    import_root = "."                     # the folder module names are relative to ("src" for a src layout)
    overrides = {"mypkg.core.field" = "mypkg/core/field.pyi"}

Only the docstrings of the stub's top-level functions, classes and their methods change: everything else in
the stub is kept byte for byte. A docstring already in the stub is replaced (the compiled one wins), so
re-running changes nothing. Commands: ``list``, ``sync`` (write), ``check`` (exit 1 when a stub is out of
date, for CI). A module that cannot be imported (extensions not built) is reported and exits 2.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import typer

from .config import ConfigError, root_path, typed
from .paths import ROOT, shown

__all__ = ["Target", "discover", "render", "register"]

_BOILERPLATE_DOCS = {inspect.getdoc(object.__init__), inspect.getdoc(object.__call__)}
WHERE = "tool.devkit.pyi"


@dataclass(frozen=True)
class Target:
    """One compiled module and the stub its docstrings go to."""

    module: str
    stub: Path


def discover(packages: list[str], import_root: Path, overrides: dict[str, str]) -> list[Target]:
    """Every ``*.pyx`` under ``packages`` with a same-stem ``.pyi`` beside it, then ``overrides`` applied
    (module -> stub path relative to the repository root; ``""`` drops the module). Sorted by module."""
    found: dict[str, Path] = {}
    for package in packages:
        folder = Path(root_path(package))
        if not folder.is_dir():
            raise ConfigError(f"[{WHERE}] packages: {package!r} is not a folder under {ROOT}")
        for pyx in folder.rglob("*.pyx"):
            stub = pyx.with_suffix(".pyi")
            if stub.is_file():
                found[_module_name(pyx, import_root)] = stub
    for module, stub in overrides.items():
        if not stub:
            found.pop(module, None)
            continue
        path = Path(root_path(stub))
        if not path.is_file():
            raise ConfigError(f"[{WHERE}] overrides: stub {stub!r} of {module!r} does not exist")
        found[module] = path
    return [Target(m, found[m]) for m in sorted(found)]


def _module_name(source: Path, import_root: Path) -> str:
    """The dotted module name of ``source`` relative to ``import_root``."""
    try:
        rel = source.with_suffix("").relative_to(import_root)
    except ValueError as exc:
        raise ConfigError(f"[{WHERE}] {source} is outside import_root {import_root}") from exc
    return ".".join(rel.parts)


def _doc_table(mod: ModuleType) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """``{function: doc}`` for ``mod``'s public functions and ``{class: {"": class_doc, method: doc}}`` for its
    public classes (names ``mod`` merely imports are skipped)."""
    funcs: dict[str, str] = {}
    classes: dict[str, dict[str, str]] = {}
    for name, obj in vars(mod).items():
        if name.startswith("_") or getattr(obj, "__module__", None) != mod.__name__:
            continue
        if inspect.isclass(obj):
            methods = {"": inspect.getdoc(obj) or ""}
            for mname, member in vars(obj).items():
                if mname.startswith("__") and mname not in ("__init__", "__call__"):
                    continue
                doc = inspect.getdoc(member)
                if doc and doc not in _BOILERPLATE_DOCS:
                    methods[mname] = doc
            classes[name] = methods
        elif inspect.isfunction(obj) or inspect.isbuiltin(obj):
            doc = inspect.getdoc(obj)
            if doc:
                funcs[name] = doc
    return funcs, classes


def _quote(doc: str, indent: str) -> list[str]:
    """``doc`` as indented triple-quoted lines: one line when ``doc`` has no newline, else opening / body /
    closing lines. Raw (``r'''``) when ``doc`` holds a backslash, so it reads back unchanged."""
    q = "'''" if '"""' in doc else '"""'
    r = "r" if "\\" in doc else ""
    lines = doc.splitlines()
    if len(lines) == 1:
        return [f"{indent}{r}{q}{lines[0]}{q}"]
    return [f"{indent}{r}{q}"] + [f"{indent}{ln}" if ln else "" for ln in lines] + [f"{indent}{q}"]


def _docstring_span(node: ast.ClassDef | ast.FunctionDef) -> tuple[int, int] | None:
    """``(first, last)`` line (1-based, inclusive) of ``node``'s leading string statement, or ``None``."""
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[0].lineno, body[0].end_lineno or body[0].lineno
    return None


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def render(module: ModuleType, src: str) -> tuple[str, int]:
    """``src`` (a stub's text) with ``module``'s docstrings in place, and how many docstrings were placed."""
    funcs, classes = _doc_table(module)
    lines = src.splitlines()
    tree = ast.parse(src)
    # edits as (first, last, new lines), 1-based inclusive (last < first: insert before `first`), applied
    # bottom-up so earlier edits keep their line numbers
    edits: list[tuple[int, int, list[str]]] = []

    def place(node: ast.ClassDef | ast.FunctionDef, doc: str | None) -> None:
        if not doc:
            return
        indent = _indent_of(lines[node.lineno - 1]) + "    "
        new = _quote(doc, indent)
        span = _docstring_span(node)
        if span:
            edits.append((span[0], span[1], new))
            return
        body0 = node.body[0]
        line = lines[body0.lineno - 1]
        prefix = line[: body0.col_offset]
        if prefix.strip().endswith(":"):
            # one-line stub (`def f(...) -> X: ...`): split it into signature / docstring / body
            body_text = line[body0.col_offset :].rstrip()
            edits.append((body0.lineno, body0.lineno, [prefix.rstrip(), *new, f"{indent}{body_text}"]))
        else:
            edits.append((body0.lineno, body0.lineno - 1, new))

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name in funcs:
            place(node, funcs[node.name])
        elif isinstance(node, ast.ClassDef) and node.name in classes:
            methods = classes[node.name]
            place(node, methods.get(""))
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.FunctionDef) and child.name in methods:
                    place(child, methods[child.name])

    edits.sort(key=lambda e: e[0], reverse=True)
    for first, last, new in edits:
        lines[first - 1 : last] = new
    return "\n".join(lines) + "\n", len(edits)


def _configured() -> tuple[list[Target], Path]:
    """The targets ``[tool.devkit.pyi]`` finds, and the folder their module names are relative to."""
    import_root = Path(root_path(typed(_CONFIG, "import_root", str, ".", WHERE)))
    packages = typed(_CONFIG, "packages", list, [], WHERE)
    return discover(packages, import_root, typed(_CONFIG, "overrides", dict, {}, WHERE)), import_root


def _run(write: bool) -> int:
    """Sync (``write``) or check every discovered stub; the exit code (0 fine, 1 out of date, 2 errors)."""
    targets, import_root = _configured()
    if not targets:
        typer.echo("no stubs: no *.pyx with a matching .pyi under the configured packages")
        return 0
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))
    stale: list[Path] = []
    errors: list[str] = []
    for t in targets:
        rel = shown(t.stub)
        try:
            module = importlib.import_module(t.module)
        except Exception as exc:  # report every unimportable module, then go on
            errors.append(
                f"{t.module}: cannot import ({type(exc).__name__}: {exc}); build the extensions first"
            )
            continue
        src = t.stub.read_text(encoding="utf-8")
        try:
            out, n = render(module, src)
        except SyntaxError as exc:
            errors.append(f"{rel}: not valid Python ({exc})")
            continue
        if out == src:
            typer.echo(f"{rel}: up to date ({n} docstring(s))")
            continue
        stale.append(rel)
        if write:
            t.stub.write_text(out, encoding="utf-8", newline="\n")
            typer.echo(f"{rel}: {n} docstring(s) synced")
        else:
            typer.echo(f"{rel}: OUT OF DATE")
    for e in errors:
        typer.echo(f"error: {e}", err=True)
    if errors:
        return 2
    if stale and not write:
        typer.echo(f"{len(stale)} stub(s) out of date: python scripts/dev.py pyi sync", err=True)
        return 1
    return 0


_CONFIG: dict[str, Any] = {}
app = typer.Typer(
    name="pyi", no_args_is_help=True, help="Docstrings of compiled (Cython) modules into their .pyi stubs."
)


@app.command("list")
def list_() -> None:
    """The compiled modules and the stubs their docstrings go to."""
    targets, _ = _configured()
    for t in targets:
        typer.echo(f"{t.module:48s} {shown(t.stub)}")
    typer.echo(f"{len(targets)} stub(s)")


@app.command()
def sync() -> None:
    """Write the compiled modules' docstrings into their stubs (run after editing a .pyx docstring)."""
    raise typer.Exit(_run(write=True))


@app.command()
def check() -> None:
    """Exit 1 when a stub's docstrings differ from its compiled module's (CI), 2 when a module cannot import."""
    raise typer.Exit(_run(write=False))


def register(root_app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``pyi`` group to ``root_app``, configured by ``[tool.devkit.pyi]`` (``cfg``)."""
    _CONFIG.clear()
    _CONFIG.update(cfg)
    root_app.add_typer(app)
