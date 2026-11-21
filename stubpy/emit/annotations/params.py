"""
Formatting of a single parameter as stub text.
"""
from __future__ import annotations

import ast
import builtins
import dataclasses
import inspect
import re
from pathlib import Path
from typing import Any

from stubpy._constants import TYPING_CANDIDATES
from stubpy.analysis import vfs
from stubpy.resolve import function_info_of
from stubpy.state.context import StubContext

from .defaults import NonLiteralDefault, default_to_str, module_attribute_default
from .registry import annotation_to_str
from .source import source_annotation
from .style import style_text

_INITVAR_RE = re.compile(r"^(?:dataclasses\.)?InitVar\[(.*)\]$")


def raw_key(param: inspect.Parameter) -> str:
    """Return the source-annotation key of *param*: its name, ``*args`` or ``**kwargs``."""
    if param.kind == inspect.Parameter.VAR_POSITIONAL:
        return f"*{param.name}"
    if param.kind == inspect.Parameter.VAR_KEYWORD:
        return f"**{param.name}"
    return param.name


def _raw_preserves_aliases(raw: str, ctx: StubContext) -> bool:
    """Return ``True`` if *raw* references a registered alias module (e.g. ``types.Color``)."""
    for module_alias in ctx.type_module_imports:
        if f"{module_alias}." in raw:
            return True
    return False


def unwrap_initvar(annotation: Any) -> Any:
    """Return ``T`` for ``InitVar[T]`` (an object, or the text Python 3.10 leaves unevaluated); else *annotation*."""
    if isinstance(annotation, dataclasses.InitVar):
        return annotation.type
    if isinstance(annotation, str):
        match = _INITVAR_RE.match(annotation.strip())
        if match:
            return match.group(1)
    return annotation


def _outside_subscripts(node: ast.AST) -> list[ast.AST]:
    """*node* and its descendants, not looking inside a subscript's brackets (where tuples are fine)."""
    found = [node]
    for child in ast.iter_child_nodes(node):
        if not (isinstance(node, ast.Subscript) and child is node.slice):
            found += _outside_subscripts(child)
    return found


def is_plain_annotation(text: str) -> bool:
    """Return ``True`` when *text* is an annotation built only from builtins, ``typing`` names and ``None``.

    Docstring types that pass are written as real annotations; others stay comments.

    Examples
    --------
    >>> is_plain_annotation("list[int] | None"), is_plain_annotation("array-like")
    (True, False)
    >>> is_plain_annotation("dict[str, int]"), is_plain_annotation("None | (int, int)")
    (True, False)
    """
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return False
    if any(isinstance(n, (ast.Tuple, ast.List)) for n in _outside_subscripts(tree.body)):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if not (hasattr(builtins, node.id) or node.id in TYPING_CANDIDATES):
                return False
        elif not isinstance(node, (ast.Expression, ast.Subscript, ast.BinOp, ast.BitOr, ast.Tuple, ast.List,
                                   ast.Load, ast.Constant)):
            return False
    return True


def _source_default_text(param: inspect.Parameter, owner: Any, ctx: StubContext) -> str | None:
    """Return the source text of an evaluated default that reads a module attribute (``os.sep``)."""
    if owner is None or param.default is inspect.Parameter.empty or isinstance(param.default, NonLiteralDefault):
        return None
    info = function_info_of(owner)
    raw = next((rp.default_repr for rp in info.raw_params if rp.name == param.name), None) if info else None
    return module_attribute_default(raw, getattr(owner, "__globals__", None), ctx)


def _bound_from_source(text: str, owner: Any, ctx: StubContext) -> bool:
    """Bind the names of an unevaluated annotation written in another module (a ``TYPE_CHECKING`` import)."""
    namespace = getattr(owner, "__globals__", None)
    if not isinstance(namespace, dict) or namespace is ctx.module_namespace:
        return True
    if ctx.source_index is None or ctx.source_module is None:
        return True
    from stubpy.emit._static import bind_names, names_in

    file = getattr(getattr(owner, "__code__", None), "co_filename", None)
    there = ctx.source_index.module_at(file) if file and vfs.is_file(Path(file)) else None
    names = names_in(text)
    if there is None or names is None:
        return True
    return bind_names(names, there, ctx)


def format_param(
    param: inspect.Parameter,
    hints: dict[str, Any],
    ctx: StubContext,
    raw_ann_override: str | None = None,
    docstring_type: str | None = None,
    inferred_type: str | None = None,
) -> str:
    """Format *param* as ``name: Type = default`` (or ``*name`` / ``**name``).

    The annotation comes from the source text when that keeps an alias
    name, from *raw_ann_override* when it names an alias module, else from
    *hints*, else from ``param.annotation``.  Without one, *inferred_type*
    is used as a real annotation, and so is a *docstring_type* made only of
    builtins and ``typing`` names; any other docstring type is appended as a
    ``# type:`` comment (the signature is then laid out one parameter per
    line, so the comment never swallows code).

    Examples
    --------
    >>> p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ...                       annotation=int, default=0)
    >>> format_param(p, {}, StubContext())
    'x: int = 0'
    """
    name = param.name
    owner = getattr(hints, "owner", None)
    default_str = _source_default_text(param, owner, ctx) or default_to_str(param.default, ctx)

    key = raw_key(param)
    key = getattr(hints, "source_names", {}).get(key, key)
    source_text = source_annotation(owner, key, ctx) if owner is not None else None
    if source_text is not None:
        ann_str = source_text
    elif raw_ann_override is not None and _raw_preserves_aliases(raw_ann_override, ctx):
        ann_str = style_text(raw_ann_override, ctx)
        for module_alias, import_stmt in ctx.type_module_imports.items():
            if f"{module_alias}." in raw_ann_override:
                ctx.used_type_imports[module_alias] = import_stmt
    else:
        value = unwrap_initvar(hints.get(name, param.annotation))
        ann_str = annotation_to_str(value, ctx)
        if isinstance(value, str) and ann_str and not _bound_from_source(ann_str, owner, ctx):
            ann_str = ""

    doc_comment = ""
    if not ann_str:
        if inferred_type:
            ann_str = inferred_type
        elif docstring_type and is_plain_annotation(docstring_type):
            ann_str = docstring_type
            if param.default is None and "None" not in ann_str:
                ann_str += " | None"
        elif docstring_type:
            doc_comment = f"  # type: {docstring_type}"

    if param.kind == inspect.Parameter.VAR_POSITIONAL:
        return f"*{name}" + (f": {ann_str}" if ann_str else "") + doc_comment
    if param.kind == inspect.Parameter.VAR_KEYWORD:
        return f"**{name}" + (f": {ann_str}" if ann_str else "") + doc_comment

    if not ann_str:
        return name + (f"={default_str}" if default_str else "") + doc_comment
    return f"{name}: {ann_str}" + (f" = {default_str}" if default_str else "") + doc_comment
