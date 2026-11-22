"""
Rendering of default values: a valid literal, an in-scope name, or ``...``.
"""
from __future__ import annotations

import ast
import builtins
import enum
import inspect
import math
import types
from typing import Any

from stubpy._constants import ENUM_BASE_NAMES, TARGET_MODULE_PREFIX
from stubpy.analysis.harvest.models import NonLiteralDefault
from stubpy.analysis.origins import relative_module
from stubpy.emit._constants import MAX_DEFAULT_CONTAINER_ITEMS, MAX_DEFAULT_INT_BITS, MAX_DEFAULT_LITERAL_LEN
from stubpy.state.context import StubContext

ELLIPSIS = "..."

__all__ = [
    "ELLIPSIS", "NonLiteralDefault", "default_to_str", "literal_arg", "module_attribute_default", "name_in_scope",
    "render_default",
]


def _literal(value: Any, depth: int, limit: bool) -> str | None:
    """Return *value* as literal source text, or ``None`` when it is not a plain literal."""
    kind = type(value)
    if value is None or kind is bool:
        return repr(value)
    if kind is int:
        return repr(value) if value.bit_length() <= MAX_DEFAULT_INT_BITS else None
    if kind is float:
        return repr(value) if math.isfinite(value) else None
    if kind is complex:
        return repr(value) if math.isfinite(value.real) and math.isfinite(value.imag) else None
    if kind in (str, bytes):
        text = repr(value)
        return text if not limit or len(text) <= MAX_DEFAULT_LITERAL_LEN else None
    if depth >= 2 or kind not in (tuple, list, dict) or len(value) > MAX_DEFAULT_CONTAINER_ITEMS:
        return None
    if kind is dict:
        items = [(_literal(k, depth + 1, limit), _literal(v, depth + 1, limit)) for k, v in value.items()]
        if any(k is None or v is None for k, v in items):
            return None
        return "{" + ", ".join(f"{k}: {v}" for k, v in items) + "}"
    parts = [_literal(v, depth + 1, limit) for v in value]
    if any(p is None for p in parts):
        return None
    if kind is list:
        return "[" + ", ".join(parts) + "]"  # type: ignore[arg-type]
    return "(" + ", ".join(parts) + ("," if len(parts) == 1 else "") + ")"  # type: ignore[arg-type]


def builtin_type_name(obj: Any, ctx: StubContext | None) -> str | None:
    """Return the stub name of a type defined in C: its builtin name, or ``types.X`` (importing :mod:`types`).

    ``types.ModuleType`` reports ``builtins.module``, which is not a name in scope.
    """
    name = getattr(obj, "__name__", None)
    if isinstance(name, str) and getattr(builtins, name, None) is obj:
        return name
    exported = next((n for n, v in vars(types).items() if v is obj and not n.startswith("_")), None)
    if exported is None:
        return None
    if ctx is not None:
        ctx.extra_imports["types"] = "import types"
    return f"types.{exported}"


def name_in_scope(obj: Any, ctx: StubContext | None) -> str | None:
    """Return the stub expression naming class *obj*, registering its import, or ``None``.

    Builtins and classes of the current module need no import; otherwise the
    source's own import is reused, or an absolute import is added when the
    defining module is importable.
    """
    qualname = getattr(obj, "__qualname__", None)
    module = getattr(obj, "__module__", None)
    if ctx is None:
        return qualname if isinstance(qualname, str) and "<" not in qualname else getattr(obj, "__name__", None)
    if not isinstance(qualname, str) or not isinstance(module, str) or "<" in qualname:
        return None
    if module == "builtins":
        return builtin_type_name(obj, ctx)
    head = qualname.split(".")[0]
    if module == ctx.module_name or ctx.module_namespace.get(head) is obj and _defined_in_source(head, ctx):
        return qualname
    if _shadowed(head, obj, ctx) and all(part.isidentifier() for part in module.split(".")):
        return _module_qualified(module, qualname, ctx)
    stmt = ctx.import_map.get(head)
    if stmt is not None and not stmt.endswith("*"):
        ctx.extra_imports[head] = stmt
        bound = ctx.module_namespace.get(head) if ctx.module_namespace else None
        if isinstance(bound, types.ModuleType) and bound is not obj and getattr(bound, "__name__", None) == module:
            return f"{head}.{qualname}"
        return qualname
    if module.startswith(TARGET_MODULE_PREFIX) or module == "__main__" or not all(
        part.isidentifier() for part in module.split(".")
    ):
        return None
    source = relative_module(module, ctx.module_name, "__path__" in ctx.module_namespace)
    ctx.extra_imports[head] = f"from {source} import {head}"
    return qualname


def _defined_in_source(name: str, ctx: StubContext) -> bool:
    """True when the module's own source defines class *name* (its ``__module__`` may name a public package).

    A ``Name = module.Class`` alias counts: the stub writes it, so *name* is bound there.
    """
    table = ctx.symbol_table
    sym = table.get(name) if table is not None else None
    if sym is None and table is not None:
        hidden = table.get(name, hidden=True)
        sym = hidden if type(hidden).__name__ == "VariableSymbol" else None
    info = getattr(sym, "ast_info", None)
    if sym is None or info is None:
        return False
    if type(sym).__name__ == "ClassSymbol":
        return True
    if type(sym).__name__ != "VariableSymbol":
        return False
    module = ctx.source_module
    values = [v.value_repr for v in module.symbols.variables if v.name == name] if module is not None else []
    return any(_dotted_name(v) for v in [getattr(info, "value_repr", None), *values])


def _dotted_name(value: str | None) -> bool:
    return bool(value) and "." in value and all(part.isidentifier() for part in value.split("."))


def _shadowed(head: str, obj: Any, ctx: StubContext) -> bool:
    """True when the current module defines its own *head*, so the imported class cannot keep that name."""
    local = ctx.module_namespace.get(head)
    return local is not None and local is not obj and getattr(local, "__module__", None) == ctx.module_name


def _module_qualified(module: str, qualname: str, ctx: StubContext) -> str:
    """Import *module* itself and return ``module_tail.Qualname`` (``from .. import _ext`` then ``_ext.Cls``).

    The module is imported from its parent package, also when that module is the current
    module's own package (``from dpk import parsers`` in ``dpk.parsers.null``).
    """
    parent, _, tail = module.rpartition(".")
    if parent:
        source = relative_module(parent, ctx.module_name, "__path__" in ctx.module_namespace)
        ctx.extra_imports[tail] = f"from {source} import {tail}"
    else:
        ctx.extra_imports[tail] = f"import {tail}"
    return f"{tail}.{qualname}"


def _enum_member(value: enum.Enum, ctx: StubContext | None) -> str | None:
    """Return ``Cls.MEMBER`` for an enum member reachable by name, else ``None`` (also for another module's private enum)."""
    name = value.name
    if type(value).__name__.startswith("_") and type(value).__module__ != getattr(ctx, "module_name", None):
        return None
    if not isinstance(name, str) or not name.isidentifier():
        return None
    try:
        if type(value)[name] is not value:
            return None
    except Exception:
        return None
    cls_text = name_in_scope(type(value), ctx)
    return f"{cls_text}.{name}" if cls_text else None


def _local_enum_names(ctx: StubContext | None) -> set[str]:
    """Return the names of enum classes defined in the module, from the symbol table."""
    table = getattr(ctx, "symbol_table", None) if ctx is not None else None
    if table is None:
        return set()
    names: set[str] = set()
    for cls_sym in table.classes():
        info = cls_sym.ast_info
        if info is not None and any(b.rpartition(".")[2] in ENUM_BASE_NAMES for b in info.bases):
            names.add(cls_sym.name)
    return names


def _local_member(owner: str, name: str, ctx: StubContext | None) -> bool:
    """True when ``owner.name`` is a member of a local enum, or an attribute of a local class typed as that class."""
    if owner in _local_enum_names(ctx):
        return True
    table = getattr(ctx, "symbol_table", None) if ctx is not None else None
    sym = table.get_class(owner) if table is not None else None
    info = sym.ast_info if sym is not None else None
    own_type = {owner, f"ClassVar[{owner}]"}
    return info is not None and any(a.name == name and a.annotation_str in own_type for a in info.attributes)


def _is_private(name: str) -> bool:
    """True for a ``_name`` that is not a dunder: a private sentinel never belongs in a public stub."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _source_default(text: str, ctx: StubContext | None) -> str | None:
    """Keep an AST-only default that names something in scope: ``LocalEnum.MEMBER`` or an imported name.

    Imported names (``os.sep``, ``Mode.FAST`` after ``from m import Mode``)
    get their import recorded in *ctx*; private names (``np._NoValue``) and
    anything else give ``None``.
    """
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    root = node
    parts: list[str] = []
    while isinstance(root, ast.Attribute):
        parts.append(root.attr)
        root = root.value
    if isinstance(root, ast.Name):
        parts.append(root.id)
    if any(_is_private(part) for part in parts):
        return None
    if not isinstance(root, ast.Name) or (root is node and ctx is None):
        return None
    if root is not node and isinstance(node.value, ast.Name) and _local_member(root.id, node.attr, ctx):
        return text
    stmt = (ctx.import_map.get(root.id) or ctx.extra_imports.get(root.id) or next(
        (v for k, v in ctx.extra_imports.items() if k.split(".")[0] == root.id and v.startswith("import ")), None,
    )) if ctx is not None else None
    if stmt is None or stmt.endswith("*"):
        return None
    ctx.extra_imports[root.id] = stmt  # type: ignore[union-attr]
    return text


def render_default(value: Any, ctx: StubContext | None = None) -> str:
    """Render a default value as stub text that always parses.

    Plain literals (``None``, bools, ints, finite floats, strings, bytes and
    small containers of these) are written as literals; enum members as
    ``Cls.MEMBER`` and classes by name when they are in scope (adding the
    import to *ctx*); everything else, including sentinels, ``inf``/``nan``
    and huge ints, as ``...``.

    Parameters
    ----------
    value : Any
        The default value.
    ctx : StubContext, optional
        Run context used to check names are in scope and to record imports.

    Returns
    -------
    str
        Source text for the default.

    Examples
    --------
    >>> render_default("it's")
    '"it\\'s"'
    >>> render_default(float("inf"))
    '...'
    >>> render_default(object())
    '...'
    """
    if isinstance(value, NonLiteralDefault):
        return _source_default(repr(value), ctx) or ELLIPSIS
    if isinstance(value, enum.Enum):
        return _enum_member(value, ctx) or ELLIPSIS
    if isinstance(value, type):
        return name_in_scope(value, ctx) or ELLIPSIS
    return _literal(value, 0, limit=True) or ELLIPSIS


def literal_arg(value: Any, ctx: StubContext | None = None) -> str | None:
    """Render one ``Literal[...]`` argument without length limits; ``None`` when impossible."""
    if isinstance(value, enum.Enum):
        return _enum_member(value, ctx)
    return _literal(value, 0, limit=False)


def default_to_str(default: Any, ctx: StubContext | None = None) -> str:
    """Render a parameter default as stub text; ``""`` for ``inspect.Parameter.empty``.

    Examples
    --------
    >>> default_to_str("black")
    "'black'"
    >>> default_to_str(None)
    'None'
    """
    if default is inspect.Parameter.empty:
        return ""
    return render_default(default, ctx)


def module_attribute_default(text: str | None, namespace: Any, ctx: StubContext) -> str | None:
    """Return a source default such as ``os.sep`` when it reads an attribute of an imported module, else ``None``.

    The evaluated value can depend on the platform (``os.sep``) or hide the
    name (``math.pi``); the source text keeps it.  The module is imported in
    the stub as the source imports it.
    """
    if not text or not isinstance(namespace, dict):
        return None
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Attribute):
        return None
    root = node
    while isinstance(root, ast.Attribute):
        root = root.value
    if not isinstance(root, ast.Name):
        return None
    module = namespace.get(root.id)
    if not isinstance(module, types.ModuleType) or module.__name__ != root.id:
        return None
    if ctx.module_namespace.get(root.id, module) is not module:
        return None
    ctx.extra_imports.setdefault(root.id, f"import {root.id}")
    return text
