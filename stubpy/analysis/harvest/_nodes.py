"""
Small AST node helpers shared by the harvester.
"""
from __future__ import annotations

import ast
import importlib.util

from stubpy.analysis._constants import KNOWN_TYPE_NAMES

from ._calls import call_func_name

_TYPEVAR_CALL_NAMES: frozenset[str] = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple", "NewType", "TypedDict", "NamedTuple", "namedtuple"})


def children(node: ast.AST) -> list[ast.AST]:
    """Return :func:`ast.iter_child_nodes` of *node* as a list, minus ``Load`` / ``Store`` contexts."""
    out: list[ast.AST] = []
    for name in node._fields:
        if name == "ctx":
            continue
        value = getattr(node, name, None)
        if isinstance(value, ast.AST):
            out.append(value)
        elif isinstance(value, list):
            out.extend(item for item in value if isinstance(item, ast.AST))
    return out


def unparse(node: ast.expr | None) -> str | None:
    """Unparse *node* to source text, or return ``None``."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def type_params(node: ast.AST) -> list[str]:
    """Return the PEP 695 type parameters of a ``def`` / ``class`` / ``type`` node as source text."""
    return [t for t in (unparse(p) for p in getattr(node, "type_params", None) or ()) if t]


def decorator_name(node: ast.expr) -> str:
    """Return the simple name of ``@name`` / ``@mod.name`` / ``@name(...)`` decorators, else ``""``."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def is_stub_body(body: list[ast.stmt]) -> bool:
    """Return ``True`` when *body* only holds a docstring, ``pass``, ``...`` or ``raise NotImplementedError``."""
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                continue
        return False
    return True


def is_main_guard(test: ast.expr) -> bool:
    """Return ``True`` for the test of ``if __name__ == "__main__":``."""
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def is_implicit_alias(node: ast.expr | None) -> bool:
    """Return ``True`` for an unannotated RHS that is unambiguously a type.

    That is a PEP 604 union or a subscript of type-like parts, or a known builtin/typing name.
    A type-like part is a known type name, a CapWords name (``Path``, ``np.ndarray`` is not),
    ``None`` or a string. ``version.split("+")[0]`` and ``O_RDONLY | O_CREAT`` are values.

    Examples
    --------
    >>> [is_implicit_alias(ast.parse(s, mode="eval").body) for s in (
    ...     "int | None", "list[Path]", "Callable[[int], str]", "version.split('+')[0]", "O_RDONLY | O_CREAT",
    ...     "table['key']", "cfg.data['k']", "np.ndarray[Any, np.dtype[np.float64]]")]
    [True, True, True, False, False, False, False, True]
    """
    if isinstance(node, (ast.BinOp, ast.Subscript)):
        return _type_like(node)
    return isinstance(node, ast.Name) and node.id in KNOWN_TYPE_NAMES


def _type_like(node: ast.expr) -> bool:
    """True when *node* reads as a type expression."""
    if isinstance(node, ast.BinOp):
        return isinstance(node.op, ast.BitOr) and _type_like(node.left) and _type_like(node.right)
    if isinstance(node, ast.Subscript):
        if not (_type_name(node.value) or isinstance(node.value, ast.Attribute) and _dotted(node.value)):
            return False
        literal = (node.value.attr if isinstance(node.value, ast.Attribute) else getattr(node.value, "id", "")) in (
            "Literal", "Annotated")
        items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if not _type_name(node.value) and any(isinstance(i, ast.Constant) for i in items):
            return False
        head = node.value.attr if isinstance(node.value, ast.Attribute) else getattr(node.value, "id", "")
        loose = head in KNOWN_TYPE_NAMES and not literal
        return all(literal or _slice_item(i, loose) for i in items)
    if isinstance(node, ast.Constant):
        return node.value is None or isinstance(node.value, str)
    return _type_name(node)


def _slice_item(node: ast.expr, loose: bool = False) -> bool:
    """One item inside a type's brackets: a type, ``...``, or a ``[...]`` list of types (``Callable``).

    Inside a known type's brackets (*loose*: ``Union[dt_tzinfo, str]``, ``Mapping[istr, str]``) every
    name is a type, whatever its case.
    """
    if isinstance(node, ast.Constant) and node.value is Ellipsis:
        return True
    if isinstance(node, ast.List):
        return all(_slice_item(e, loose) for e in node.elts)
    if isinstance(node, ast.Name) and (loose or node.id.lstrip("_")[:1].isupper()):
        return True
    if loose and isinstance(node, ast.Attribute) and _dotted(node):
        return True
    if loose and isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _slice_item(node.left, loose) and _slice_item(node.right, loose)
    return _type_like(node) or isinstance(node, ast.Attribute) and _dotted(node)


def _dotted(node: ast.expr) -> bool:
    """``a.b.c``: names joined by dots, no calls or subscripts."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name)


def _type_name(node: ast.expr) -> bool:
    """A known type name or a CapWords name, possibly dotted (``Path``, ``typing.Any``, ``int``)."""
    if isinstance(node, ast.Attribute):
        last = node.attr
    elif isinstance(node, ast.Name):
        last = node.id
    else:
        return False
    bare = last.lstrip("_")
    return last in KNOWN_TYPE_NAMES or (bare[:1].isupper() and any(c.islower() for c in bare))


def typevar_call_kind(node: ast.expr | None) -> str | None:
    """Return ``"TypeVar"`` / ``"ParamSpec"`` / ... when *node* calls one, else ``None``."""
    if not isinstance(node, ast.Call):
        return None
    name = call_func_name(node).rpartition(".")[2]
    return name if name in _TYPEVAR_CALL_NAMES else None


def findable(stmt: ast.Import | ast.ImportFrom) -> bool:
    """Return ``True`` when the top-level package of the import can be found (relative imports always can)."""
    if isinstance(stmt, ast.ImportFrom) and stmt.level:
        return True
    names = [stmt.module or ""] if isinstance(stmt, ast.ImportFrom) else [a.name for a in stmt.names]
    try:
        return all(importlib.util.find_spec(n.split(".")[0]) is not None for n in names if n)
    except (ImportError, ValueError):
        return False


def catches_import_error(handler: ast.ExceptHandler) -> bool:
    """Return ``True`` for ``except ImportError`` / ``ModuleNotFoundError`` (alone or in a tuple)."""
    kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(k, ast.Name) and k.id in ("ImportError", "ModuleNotFoundError") for k in kinds)
