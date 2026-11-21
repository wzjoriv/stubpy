"""
Compare a hand-written stub with its module: missing and extra names, class members and parameter lists.
"""
from __future__ import annotations

import ast
import inspect
import types
from pathlib import Path
from typing import Any

from ..._constants import POS_ONLY, VAR_KW, VAR_POS
from ..capi import capi_signatures


def verify_stub(stub: Path, module: types.ModuleType) -> list[str]:
    """Return one line per difference between the hand-written *stub* and the imported *module*.

    Names starting with ``_`` are skipped (dunders too, except ``__init__``). Parameter lists are
    compared only where the module states them: ``__text_signature__`` (``inspect.signature``)
    or the C sources beside it.

    Parameters
    ----------
    stub : pathlib.Path
        The ``.pyi`` file.
    module : types.ModuleType
        The module it describes.

    Returns
    -------
    list of str
        ``"missing from stub: name"``, ``"not in module: name"`` and
        ``"name: stub (a, b), module (a, b, c)"`` lines; empty when they agree.

    Raises
    ------
    SyntaxError
        If the stub does not parse.
    """
    tree = ast.parse(stub.read_text(encoding="utf-8"))
    stub_defs = _definitions(tree.body)
    names = getattr(module, "__all__", None) or [n for n in vars(module) if not n.startswith("_")]
    runtime = {n: getattr(module, n) for n in names if hasattr(module, n)}
    runtime = {n: v for n, v in runtime.items() if not isinstance(v, types.ModuleType)}
    c_sigs = {name: sig for name, (sig, _) in capi_signatures(module).items()}
    problems = [f"missing from stub: {n}" for n in runtime if n not in stub_defs]
    problems += [f"not in module: {n}" for n, node in stub_defs.items()
                 if n not in runtime and not n.startswith("_") and not hasattr(module, n) and not _stub_only(node)]
    for name, obj in runtime.items():
        node = stub_defs.get(name)
        if isinstance(node, ast.ClassDef) and isinstance(obj, type):
            members = _definitions(node.body)
            for attr in vars(obj):
                if attr.startswith("_") and attr != "__init__" or attr in members:
                    continue
                if attr == "__init__" and "__init__" not in vars(obj):
                    continue
                problems.append(f"missing from stub: {name}.{attr}")
            for attr, member in members.items():
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and attr in vars(obj):
                    problems += _compare(f"{name}.{attr}", member, getattr(obj, attr), c_sigs.get(f"{name}.{attr}"), True)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            problems += _compare(name, node, obj, c_sigs.get(name), False)
    return problems


def _definitions(body: list[ast.stmt]) -> dict[str, ast.AST]:
    """Names bound at the top of *body*, ``if`` branches and ``@overload`` groups included."""
    found: dict[str, ast.AST] = {}
    queue = list(body)
    while queue:
        node = queue.pop(0)
        if isinstance(node, ast.If):
            queue[:0] = node.body + node.orelse
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.setdefault(node.name, node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.setdefault(node.target.id, node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.asname:
                    found.setdefault(alias.asname, node)
        elif type(node).__name__ == "TypeAlias":
            found.setdefault(node.name.id, node)  # type: ignore[attr-defined]
    return found


def _compare(label: str, node: ast.FunctionDef | ast.AsyncFunctionDef, obj: Any, c_sig: Any, method: bool) -> list[str]:
    """A line when the stub's parameter names differ from the ones the module states."""
    if any(isinstance(d, ast.Name) and d.id == "overload" or isinstance(d, ast.Attribute) and d.attr == "overload"
           for d in node.decorator_list):
        return []
    stated = _runtime_params(obj, c_sig)
    if stated is None:
        return []
    args = node.args
    written = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    if method and written and written[0] in ("self", "cls"):
        written = written[1:]
    if args.vararg or args.kwarg or len(written) == len(stated) and all(
            s is None or s == w for w, s in zip(written, stated, strict=False)):
        return []
    stated = [s or "_" for s in stated]
    return [f"{label}: stub ({', '.join(written)}), module ({', '.join(stated)})"]


def _stub_only(node: ast.AST) -> bool:
    """True for stub-only bindings: imports and type aliases (``X = int | str``, ``X: TypeAlias = ...``)."""
    if isinstance(node, (ast.Import, ast.ImportFrom)) or type(node).__name__ == "TypeAlias":
        return True
    if isinstance(node, ast.AnnAssign):
        return "TypeAlias" in ast.unparse(node.annotation)
    return isinstance(node, ast.Assign) and isinstance(node.value, (ast.Name, ast.Attribute, ast.Subscript, ast.BinOp))


def _runtime_params(obj: Any, c_sig: Any) -> list[str | None] | None:
    """The parameter names the module states for *obj*, ``None`` for a positional-only one; ``None`` when unknown."""
    try:
        stated = getattr(obj, "__text_signature__", None)
        params = list(inspect.signature(obj).parameters.values()) if stated else []
    except (TypeError, ValueError):
        stated, params = None, []
    if stated:
        if params and params[0].name in ("self", "cls", "module", "type"):
            params = params[1:]
        params = [p for p in params if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        return [None if p.kind == p.POSITIONAL_ONLY else p.name for p in params]
    if c_sig is not None and all(p.kind not in (VAR_POS, VAR_KW) for p in c_sig.params):
        return [None if p.kind == POS_ONLY else p.name for p in c_sig.params]
    return None
