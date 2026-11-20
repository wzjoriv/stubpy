"""
Type aliases defined in private modules, which a stub writes as their value instead of their name.
"""
from __future__ import annotations

import ast
import sys
import types
from typing import Any

from stubpy.analysis.origins import is_named_type, origin_of
from stubpy.state.context import StubContext

from .registry import annotation_to_str

_MISSING = object()


def is_private_module(name: str) -> bool:
    """Return ``True`` when a part of the dotted module *name* starts with a single ``_``.

    Examples
    --------
    >>> is_private_module("pkg._types"), is_private_module("pkg.types"), is_private_module("__main__")
    (True, False, False)
    """
    return any(part.startswith("_") and not part.startswith("__") for part in name.split("."))


def _plain_alias(obj: Any) -> bool:
    """True for an alias value (``int | str``, ``list[int]``, ``Literal[...]``), not a ``NewType`` or ``type`` alias."""
    return is_named_type(obj) and not hasattr(obj, "__supertype__") and type(obj).__name__ != "TypeAliasType"


def _hidden_in(module_name: str, name: str) -> bool:
    """True when *name* lives in a private module that does not list it in ``__all__``."""
    if not is_private_module(module_name):
        return False
    exported = getattr(sys.modules.get(module_name), "__all__", None)
    return not isinstance(exported, (list, tuple)) or name not in exported


def _private_value(node: ast.expr, namespace: dict[str, Any]) -> Any:
    """Return the alias object *node* names when it comes from a private module that hides it, else ``_MISSING``."""
    if isinstance(node, ast.Name):
        obj = namespace.get(node.id, _MISSING)
        here = namespace.get("__name__")
        origin = origin_of(here, node.id) if isinstance(here, str) else None
        if obj is _MISSING or origin is None or origin[0] == here or not _hidden_in(*origin):
            return _MISSING
        return obj if _plain_alias(obj) else _MISSING
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        module = namespace.get(node.value.id)
        if not isinstance(module, types.ModuleType) or not _hidden_in(module.__name__, node.attr):
            return _MISSING
        obj = getattr(module, node.attr, _MISSING)
        return obj if obj is not _MISSING and _plain_alias(obj) else _MISSING
    return _MISSING


class _Inliner(ast.NodeTransformer):
    """Replace names of private aliases with their rendered values, noting whether any changed."""

    def __init__(self, namespace: dict[str, Any], ctx: StubContext) -> None:
        self.namespace, self.ctx, self.changed = namespace, ctx, False

    def _swap(self, node: ast.expr) -> ast.expr:
        obj = _private_value(node, self.namespace)
        text = annotation_to_str(obj, self.ctx) if obj is not _MISSING else ""
        try:
            value = ast.parse(text, mode="eval").body if text else None
        except SyntaxError:
            value = None
        if value is None:
            return node
        self.changed = True
        return value

    def visit_Name(self, node: ast.Name) -> ast.expr:
        return self._swap(node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        swapped = self._swap(node)
        return swapped if swapped is not node else self.generic_visit(node)


def inline_private_aliases(text: str, namespace: dict[str, Any], ctx: StubContext) -> str:
    """Return the annotation *text* with each alias from a private module replaced by its value.

    An alias counts as private when its defining module has a ``_``-prefixed part and does not
    list the alias in ``__all__``; users of the stub cannot import such a name.  Public aliases,
    ``NewType`` and ``type`` statements keep their names.

    Parameters
    ----------
    text : str
        The annotation as written in the source.
    namespace : dict
        The globals of the module the annotation was written in.
    ctx : StubContext
        The current run context; the value is rendered with its settings.

    Returns
    -------
    str
        The rewritten annotation, or *text* unchanged when it names no private alias.

    Examples
    --------
    >>> inline_private_aliases("int | None", {}, StubContext())
    'int | None'
    """
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return text
    inliner = _Inliner(namespace, ctx)
    tree = inliner.visit(tree)
    return ast.unparse(tree) if inliner.changed else text
