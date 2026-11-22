"""
Turn the fully qualified type names bindings print into stub annotations plus the imports they need.
"""
from __future__ import annotations

import ast
import builtins
import importlib.util
import sys
import types

from stubpy._constants import TYPING_CANDIDATES

__all__ = ["TypeMapper", "caller_annotation", "portable_annotation"]

_BARE_MODULES = frozenset({"typing", "typing_extensions", "collections.abc", "builtins"})


def _dotted(node: ast.expr) -> list[str] | None:
    """``["a", "b", "C"]`` for an ``a.b.C`` chain, else ``None``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return [node.id, *parts]


def _is_module(name: str) -> bool:
    """True when *name* is a module, checked without importing new top-level packages."""
    if name in sys.modules:
        return True
    if name.partition(".")[0] not in sys.modules:
        return False
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def module_of(parts: list[str]) -> int:
    """Count the leading segments of a dotted name that form its module.

    Parameters
    ----------
    parts : list of str
        The segments of a dotted name, e.g. ``["collections", "abc", "Sized"]``.

    Returns
    -------
    int
        The number of leading segments naming a module; at least ``1``.

    Examples
    --------
    >>> module_of(["collections", "abc", "Sized"])
    2
    >>> module_of(["typing", "Any"])
    1
    """
    for i in range(len(parts) - 1, 0, -1):
        if _is_module(".".join(parts[:i])):
            return i
    for i, part in enumerate(parts[:-1]):
        if part[:1].isupper():
            return max(i, 1)
    return max(len(parts) - 1, 1)


def _module_import(name: str, stmt: str) -> str:
    """*stmt*, or ``import real as name`` when it imports *name* from a module that holds it as a module.

    A stub does not re-export a plain import, so ``from pkg._typing import npt`` (``npt`` being
    ``numpy.typing`` there) is written as ``import numpy.typing as npt``.
    """
    head, _, tail = stmt.partition(" import ")
    if not head.startswith("from ") or head.startswith("from ."):
        return stmt
    value = getattr(sys.modules.get(head[5:].strip()), tail.split(" as ")[0].strip(), None)
    if not isinstance(value, types.ModuleType):
        return stmt
    return f"import {value.__name__}" if value.__name__ == name else f"import {value.__name__} as {name}"


def _name_chain(parts: list[str]) -> ast.expr:
    node: ast.expr = ast.Name(id=parts[0], ctx=ast.Load())
    for part in parts[1:]:
        node = ast.Attribute(value=node, attr=part, ctx=ast.Load())
    return node


class TypeMapper(ast.NodeTransformer):
    """Rewrite annotation text for the stub of module *module_name*.

    Names from the module itself become bare (``pkg._ext.Mode`` gives
    ``Mode``), ``typing`` / ``typing_extensions`` / ``collections.abc``
    names become bare with a ``from`` import, other qualified names stay
    qualified with an ``import`` of their module, and unknown bare names
    become ``Any``.  :attr:`imports` maps each bound name to its import.

    Parameters
    ----------
    module_name : str
        The dotted name of the module the stub is for.
    local_names : set of str, optional
        Names defined in that module, kept as written.  Defaults to empty.

    Examples
    --------
    >>> m = TypeMapper("pkg._ext", {"Mode"})
    >>> m("pkg._ext.Mode | typing.SupportsInt")
    'Mode | SupportsInt'
    >>> m.imports
    {'SupportsInt': 'from typing import SupportsInt'}
    """

    def __init__(self, module_name: str, local_names: set[str] | frozenset[str] = frozenset(),
                 known_imports: dict[str, str] | None = None) -> None:
        self.module_name = module_name
        self.local_names = set(local_names)
        self.known_imports = dict(known_imports or {})
        self.imports: dict[str, str] = {}

    def __call__(self, text: str | None) -> str | None:
        if not text:
            return None
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError:
            return None
        return ast.unparse(self.visit(tree))

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        """Rewrite a dotted name: bare for the module itself and typing names, else qualified with an import."""
        parts = _dotted(node)
        if parts is None:
            return self.generic_visit(node)
        known = self.known_imports.get(parts[0])
        if known is not None:
            self.imports.setdefault(parts[0], _module_import(parts[0], known))
            return node
        own = self.module_name.split(".")
        if parts[:len(own)] == own and len(parts) > len(own):
            return _name_chain(parts[len(own):])
        split = module_of(parts)
        module, rest = ".".join(parts[:split]), parts[split:]
        if module in _BARE_MODULES and len(rest) == 1 and rest[0] not in self.local_names:
            if module != "builtins":
                self.imports.setdefault(rest[0], f"from {module} import {rest[0]}")
            return ast.Name(id=rest[0], ctx=ast.Load())
        self.imports.setdefault(module, f"import {module}")
        return node

    def visit_Name(self, node: ast.Name) -> ast.expr:
        """Keep a known bare name; replace an unknown one with ``Any``."""
        name = node.id
        if name in self.local_names or hasattr(builtins, name) or name in TYPING_CANDIDATES:
            return node
        return ast.Name(id="Any", ctx=ast.Load())


def portable_annotation(text: str | None) -> str | None:
    """Drop ``typing.`` / ``collections.abc.`` prefixes from an annotation.

    Used where no import can be added (a Python stub that inherits a
    compiled signature).

    Parameters
    ----------
    text : str or None
        The annotation text.

    Returns
    -------
    str or None
        The annotation with bare names, or ``None`` when *text* is empty,
        unparsable or names other modules.

    See Also
    --------
    caller_annotation : Rewrite with the imports it needs instead of refusing.

    Examples
    --------
    >>> portable_annotation("typing.SupportsFloat | int"), portable_annotation("numpy.ndarray")
    ('SupportsFloat | int', None)
    """
    mapper = TypeMapper("")
    mapped = mapper(text)
    if mapped is None or any(not stmt.startswith("from typing import") for stmt in mapper.imports.values()):
        return None
    return mapped


def caller_annotation(text: str | None, owner_module: str, namespace: dict) -> tuple[str | None, dict[str, str]]:
    """Rewrite an annotation for a Python module that calls into a compiled module.

    ``owner.Name`` becomes ``Name`` when *namespace* binds that same object;
    other qualified names stay qualified with an ``import``.

    Parameters
    ----------
    text : str or None
        The annotation text.
    owner_module : str
        The dotted name of the compiled module the annotation comes from.
    namespace : dict
        The calling module's namespace, mapping bound names to objects.

    Returns
    -------
    tuple of (str or None, dict of str to str)
        The rewritten annotation and the imports it needs (bound name to
        statement); ``(None, {})`` when *text* is empty, unparsable or
        names a module that cannot be found.

    See Also
    --------
    portable_annotation : The variant for places where no import can be added.

    Examples
    --------
    >>> caller_annotation("typing.SupportsFloat", "pkg._ext", {})
    ('SupportsFloat', {'SupportsFloat': 'from typing import SupportsFloat'})
    """
    if not text:
        return None, {}
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None, {}
    owner = sys.modules.get(owner_module)
    bare = {name for name, obj in namespace.items() if owner is not None and getattr(owner, name, None) is obj}
    mapper = TypeMapper("", bare)
    mapped = ast.unparse(mapper.visit(_Unqualify(owner_module.split("."), bare).visit(tree)))
    if any(stmt.startswith("import ") and not _is_module(stmt[7:]) for stmt in mapper.imports.values()):
        return None, {}
    return mapped, dict(mapper.imports)


class _Unqualify(ast.NodeTransformer):
    """Replace ``owner.Name`` by ``Name`` for the names in *bare*."""

    def __init__(self, owner: list[str], bare: set[str]) -> None:
        self.owner = owner
        self.bare = bare

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        parts = _dotted(node)
        n = len(self.owner)
        if parts and parts[:n] == self.owner and len(parts) == n + 1 and parts[-1] in self.bare:
            return ast.Name(id=parts[-1], ctx=ast.Load())
        return self.generic_visit(node)
