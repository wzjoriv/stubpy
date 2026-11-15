"""Source annotations that keep type-alias names, with the imports the receiving stub needs."""
from __future__ import annotations

import ast
import builtins
import inspect
import sys
from typing import Any

from stubpy._constants import TYPING_BACKPORTS, TYPING_CANDIDATES
from stubpy.analysis.origins import is_named_type, origin_of, relative_module
from stubpy.core.context import StubContext
from stubpy.resolve import function_info_of, get_hints_for_method

from .defaults import name_in_scope
from .registry import annotation_to_str
from .style import restyle


def _raw_text(owner: Any, key: str) -> str | None:
    """Return the source text of *owner*'s annotation for *key* (a param key or ``"return"``)."""
    name = key.lstrip("*")
    annotations = getattr(owner, "__annotations__", None)
    value = annotations.get(name) if isinstance(annotations, dict) else None
    if isinstance(value, str):
        return value
    info = function_info_of(owner)
    if info is None:
        return None
    return info.raw_return_annotation if key == "return" else info.raw_arg_annotations.get(key)


def _roots(tree: ast.expr) -> list[tuple[str, ast.expr]] | None:
    """Return ``(root_name, node)`` per name or dotted name; ``None`` when a string is not a ``Literal`` argument."""
    found: list[tuple[str, ast.expr]] = []
    literal_args: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and (
            (isinstance(node.value, ast.Name) and node.value.id == "Literal")
            or (isinstance(node.value, ast.Attribute) and node.value.attr == "Literal")
        ):
            literal_args.update(id(n) for n in ast.walk(node.slice))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in literal_args:
            return None
        if isinstance(node, ast.Name):
            found.append((node.id, node))
    return found


def _lookup(name: str, namespace: dict[str, Any]) -> Any:
    if name in namespace:
        return namespace[name]
    return getattr(builtins, name, _MISSING)


_MISSING = object()


def _bind(name: str, obj: Any, owner_ns: dict[str, Any], ctx: StubContext) -> bool:
    """Make *name* (bound to *obj* where the annotation was written) available in the stub; ``False`` if impossible."""
    if getattr(builtins, name, _MISSING) is obj:
        return True
    if (name in TYPING_CANDIDATES or name in TYPING_BACKPORTS) and getattr(obj, "__module__", "") in (
        "typing", "typing_extensions", "collections.abc", "abc", "builtins",
    ):
        return True
    here = ctx.module_namespace.get(name, _MISSING)
    if here is not _MISSING and here is not obj:
        return False
    if owner_ns is ctx.module_namespace or here is obj:
        stmt = ctx.import_map.get(name)
        if stmt is not None and not stmt.endswith("*"):
            ctx.extra_imports[name] = stmt
        return stmt is not None or here is not _MISSING
    if isinstance(obj, type):
        return name_in_scope(obj, ctx) == name
    module_name = owner_ns.get("__name__")
    origin = origin_of(module_name, name) if isinstance(module_name, str) else None
    if origin is None or not _exported(*origin):
        return False
    target, there = origin
    is_package = "__path__" in ctx.module_namespace
    source = relative_module(target, ctx.module_name, is_package)
    ctx.extra_imports[name] = f"from {source} import {there}" + (f" as {name}" if there != name else "")
    return True


def _exported(module_name: str, name: str) -> bool:
    """Return ``True`` when the stub of *module_name* will define *name*: public and in ``__all__`` if any."""
    if name.startswith("_"):
        return False
    module = sys.modules.get(module_name)
    names = getattr(module, "__all__", None) if module is not None else None
    return not isinstance(names, (list, tuple)) or name in names


def _chain_objects(tree: ast.expr, namespace: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return ``(dotted_name, object)`` for each attribute chain rooted at a name, such as ``types.Length``."""
    found: list[tuple[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        parts: list[str] = []
        cur: ast.expr = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            continue
        obj = _lookup(cur.id, namespace)
        for part in reversed(parts):
            obj = getattr(obj, part, _MISSING)
        found.append((".".join([cur.id, *reversed(parts)]), obj))
    return found


def source_annotation(owner: Any, key: str, ctx: StubContext) -> str | None:
    """Return *owner*'s annotation for *key* as written in its source, when that keeps a type-alias name.

    Runtime evaluation expands aliases (``LengthLike`` becomes
    ``Length | float | int | str``); the source text keeps them.  The text
    is used only when it names at least one alias or ``NewType`` and every
    name in it can be made available in the stub being written (imports are
    recorded in *ctx*); ``None`` otherwise, so the caller renders the
    evaluated annotation.  ``union_style`` is applied to the text.
    """
    namespace = getattr(owner, "__globals__", None)
    if not isinstance(namespace, dict) or not ctx.module_namespace:
        return None
    text = _raw_text(owner, key)
    if not text:
        return None
    try:
        tree = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    roots = _roots(tree)
    if not roots:
        return None
    objects = {name: _lookup(name, namespace) for name, _ in roots}
    if any(obj is _MISSING for obj in objects.values()):
        return None
    candidates = list(objects.items()) + _chain_objects(tree, namespace)
    if not any(is_named_type(obj) and not _is_typing_form(name, obj) for name, obj in candidates):
        return None
    snapshot = dict(ctx.extra_imports)
    if not all(_bind(name, obj, namespace, ctx) for name, obj in objects.items()):
        ctx.extra_imports.clear()
        ctx.extra_imports.update(snapshot)
        return None
    return restyle(text, getattr(ctx.config, "union_style", "modern") == "modern")


def _is_typing_form(name: str, obj: Any) -> bool:
    """Return ``True`` for ``typing`` special forms such as ``Optional`` that only look like aliases."""
    return getattr(obj, "__module__", "") in ("typing", "typing_extensions") and (
        name in TYPING_CANDIDATES or name in TYPING_BACKPORTS
    )


def hint_text(fn: Any, key: str, ctx: StubContext) -> str:
    """Render *fn*'s annotation for *key* (``"return"`` or a parameter name), keeping alias names from the source."""
    hints = get_hints_for_method(fn)
    owner = getattr(hints, "owner", None)
    text = source_annotation(owner, key, ctx) if owner is not None else None
    if text is not None:
        return text
    return annotation_to_str(hints.get(key.lstrip("*"), inspect.Parameter.empty), ctx)
