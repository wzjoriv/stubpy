"""
Annotations from a hand-written ``.pyi`` next to an extension module, used where the binding states no type.
"""
from __future__ import annotations

import ast
import types
from pathlib import Path

from stubpy.analysis import vfs

from ..detect import module_stem


def _sibling_tree(module: types.ModuleType) -> ast.Module | None:
    """The parsed ``.pyi`` beside *module*'s file, or ``None``."""
    origin = getattr(module, "__file__", None)
    if not origin:
        return None
    path = Path(origin)
    stub = path.with_name(module_stem(path) + ".pyi")
    try:
        return ast.parse(vfs.read_source(stub)) if vfs.is_file(stub) else None
    except (OSError, SyntaxError, ValueError):
        return None


def sibling_annotations(module: types.ModuleType) -> dict[str, str]:
    """``{qualified name: annotation}``: function / method / property returns and annotated class attributes.

    Empty when the module has no file or no readable stub beside it.
    """
    tree = _sibling_tree(module)
    found: dict[str, str] = {}
    if tree is not None:
        _collect(tree.body, "", found)
    return found


def sibling_aliases(module: types.ModuleType) -> dict[str, str]:
    """``{name: right-hand side}`` of the module-level type aliases in the stub beside *module*.

    Both ``X: TypeAlias = ...`` and ``type X = ...`` count.
    """
    tree = _sibling_tree(module)
    found: dict[str, str] = {}
    for node in tree.body if tree is not None else ():
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None                 and _last_name(node.annotation) == "TypeAlias":
            found[node.target.id] = ast.unparse(node.value)
        elif type(node).__name__ == "TypeAlias":
            found[node.name.id] = ast.unparse(node.value)  # type: ignore[attr-defined]
    return found


def _collect(body: list[ast.stmt], prefix: str, found: dict[str, str]) -> None:
    for node in body:
        if isinstance(node, ast.ClassDef):
            _collect(node.body, f"{prefix}{node.name}.", found)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            setter = any(isinstance(d, ast.Attribute) and d.attr in ("setter", "deleter") for d in node.decorator_list)
            if not setter:
                found.setdefault(prefix + node.name, ast.unparse(node.returns))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotation = _unqualified(node.annotation)
            if annotation is not None:
                found.setdefault(prefix + node.target.id, ast.unparse(annotation))


def _unqualified(node: ast.expr) -> ast.expr | None:
    """The type inside ``Final[...]`` / ``ClassVar[...]``; ``None`` for a bare ``Final`` (no type stated).

    Examples
    --------
    >>> ast.unparse(_unqualified(ast.parse("Final[np.ufunc]", mode="eval").body))
    'np.ufunc'
    >>> _unqualified(ast.parse("Final", mode="eval").body) is None
    True
    """
    if isinstance(node, ast.Subscript) and _last_name(node.value) in ("Final", "ClassVar"):
        return _unqualified(node.slice)
    return None if _last_name(node) in ("Final", "ClassVar") else node


def _last_name(node: ast.expr) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
