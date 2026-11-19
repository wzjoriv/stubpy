"""
Names a module provides lazily through a module-level ``__getattr__`` (PEP 562).
Reads name-to-module dicts and ``if name == "Name":`` branches from the source.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .astutil import iter_statements
from .harvest import infer_type_from_literal
from .harvest.models import ImportInfo


@dataclass
class LazyExports:
    """The lazy names a module's ``__getattr__`` answers.

    Attributes
    ----------
    lineno : int
        Line of the ``def __getattr__``.
    imports : dict of str to ImportInfo
        Each name resolved to the import that provides it, bound under that name.
    values : dict of str to str
        Names a branch returns a literal for, with the literal's type.
    names : set of str
        Every lazy name found, resolved or not.
    closed : bool
        ``__getattr__`` ends by raising, so it answers no names beyond those found.

    Examples
    --------
    >>> LazyExports(lineno=3).closed
    False
    """
    lineno: int
    imports: dict[str, ImportInfo] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)
    names: set[str] = field(default_factory=set)
    closed: bool = False


def find_getattr(tree: ast.Module) -> ast.FunctionDef | None:
    """Return the module-level ``def __getattr__``, or ``None``.

    Parameters
    ----------
    tree : ast.Module
        The parsed module.

    Returns
    -------
    ast.FunctionDef or None
        The function node, if the module defines one.

    Examples
    --------
    >>> find_getattr(ast.parse("def __getattr__(name): ...")).name
    '__getattr__'
    >>> find_getattr(ast.parse("x = 1")) is None
    True
    """
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
            return node
    return None


def static_lazy_exports(tree: ast.Module) -> LazyExports | None:
    """Return the lazy names of the module in *tree*.

    Parameters
    ----------
    tree : ast.Module
        The parsed module.

    Returns
    -------
    LazyExports or None
        The lazy names and their imports; ``None`` without a module ``__getattr__``.

    Examples
    --------
    >>> tree = ast.parse(
    ...     "_LAZY = {'Canvas': '.core'}\\n"
    ...     "def __getattr__(name):\\n"
    ...     "    if name in _LAZY:\\n"
    ...     "        return getattr(importlib.import_module(_LAZY[name], __name__), name)\\n"
    ...     "    raise AttributeError(name)\\n"
    ... )
    >>> lazy = static_lazy_exports(tree)
    >>> lazy.imports["Canvas"].module, lazy.closed
    ('.core', True)
    """
    func = find_getattr(tree)
    if func is None or not func.args.args:
        return None
    param = func.args.args[0].arg
    result = LazyExports(lineno=func.lineno, closed=bool(func.body) and isinstance(func.body[-1], ast.Raise))
    mappings = _dict_literals(tree.body) | _dict_literals(func.body)
    for stmt in iter_statements(func, enter_functions=False):
        if isinstance(stmt, ast.If):
            _read_branch(stmt, param, mappings, result)
    return result


def _dict_literals(body: list[ast.stmt]) -> dict[str, ast.Dict]:
    """Return the ``NAME = {...}`` dict literals assigned directly in *body*."""
    found: dict[str, ast.Dict] = {}
    for stmt in body:
        value = stmt.value if isinstance(stmt, (ast.Assign, ast.AnnAssign)) else None
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [getattr(stmt, "target", None)]
        if isinstance(value, ast.Dict):
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = value
    return found


def _strings(node: ast.expr) -> list[str] | None:
    """Return the string elements of a tuple / list / set literal, else ``None``."""
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return None
    items = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return items if len(items) == len(node.elts) else None


def _read_branch(node: ast.If, param: str, mappings: dict[str, ast.Dict], result: LazyExports) -> None:
    """Record the names an ``if`` testing *param* provides."""
    test = node.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.left, ast.Name)
            and test.left.id == param):
        return
    op, right = test.ops[0], test.comparators[0]
    attribute = _calls_getattr(node.body)
    if isinstance(op, ast.Eq) and isinstance(right, ast.Constant) and isinstance(right.value, str):
        keys = [right.value]
    elif isinstance(op, ast.In) and isinstance(right, ast.Name) and right.id in mappings:
        for key_node, value_node in zip(mappings[right.id].keys, mappings[right.id].values, strict=True):
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                result.names.add(key_node.value)
                imp = _from_value(key_node.value, value_node, attribute, _dots(node.body))
                if imp is not None:
                    result.imports.setdefault(key_node.value, imp)
        return
    elif isinstance(op, ast.In) and _strings(right) is not None:
        keys = _strings(right) or []
    else:
        return
    for key in keys:
        result.names.add(key)
        imp = _from_body(key, node.body, param)
        if imp is not None:
            result.imports.setdefault(key, imp)
        elif len(keys) == 1:
            returned = next((s.value for s in node.body if isinstance(s, ast.Return) and s.value is not None), None)
            literal = infer_type_from_literal(returned) if returned is not None else None
            if literal and literal != "None":
                result.values.setdefault(key, literal)


def _calls_getattr(body: list[ast.stmt]) -> bool:
    """True when *body* calls ``getattr(...)`` (the name is an attribute of the imported module)."""
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr"
        for stmt in body for n in ast.walk(stmt)
    )


def module_import(module: str, key: str) -> ImportInfo:
    """Return the import binding the module *module* as *key*.

    Parameters
    ----------
    module : str
        Module path, possibly relative (``".pkg.mod"``).
    key : str
        The local name the import binds.

    Returns
    -------
    ImportInfo
        A ``from <parent> import <last> as <key>`` import for a dotted or relative
        module, a plain ``import`` otherwise.

    Examples
    --------
    >>> info = module_import("..pkg.mod", "m")
    >>> info.module, info.name, info.asname
    ('..pkg', 'mod', 'm')
    """
    if module.startswith("."):
        stripped = module.lstrip(".")
        dots = module[:len(module) - len(stripped)]
        parent, _, last = stripped.rpartition(".")
        return ImportInfo(dots + parent, last, key)
    return ImportInfo(None, module, key)


def _dots(body: list[ast.stmt]) -> str:
    """Return the leading dots ``import_module`` prepends to mapping values (``f".{mod}"``, ``"." + mod``), else ``""``."""
    for n in (n for stmt in body for n in ast.walk(stmt)):
        func = getattr(n, "func", None)
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if not isinstance(n, ast.Call) or name != "import_module" or not n.args:
            continue
        arg = n.args[0]
        head = arg.values[0] if isinstance(arg, ast.JoinedStr) and arg.values else (
            arg.left if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add) else None)
        if isinstance(head, ast.Constant) and isinstance(head.value, str) and head.value.strip("."):
            return ""
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
    return ""


def _from_value(key: str, value: ast.expr, attribute: bool, dots: str = "") -> ImportInfo | None:
    """Resolve one mapping entry: ``"mod"``, ``"mod:attr"`` or ``("mod", "attr")``, *dots* prepended to the module."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
        module, _, attr = value.value.partition(":")
        module = dots + module
        if attr:
            return ImportInfo(module, attr, key)
        return ImportInfo(module, key, key) if attribute else module_import(module, key)
    parts = _strings(value)
    if parts is not None and len(parts) == 2 and all(parts):
        return ImportInfo(dots + parts[0], parts[1], key)
    return None


def _from_body(key: str, body: list[ast.stmt], param: str) -> ImportInfo | None:
    """Resolve a branch that imports *key* and returns it."""
    bound: dict[str, ImportInfo] = {}
    for stmt in body:
        if isinstance(stmt, ast.ImportFrom):
            module = "." * stmt.level + (stmt.module or "")
            for alias in stmt.names:
                bound[alias.asname or alias.name] = ImportInfo(module, alias.name, key)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.asname:
                    bound[alias.asname] = ImportInfo(None, alias.name, key)
        elif isinstance(stmt, ast.Return) and stmt.value is not None:
            return _returned(stmt.value, key, bound, param)
    return None


def _returned(value: ast.expr, key: str, bound: dict[str, ImportInfo], param: str) -> ImportInfo | None:
    """Resolve the returned expression: an imported name, ``import_module(...)`` or ``getattr(import_module(...), ...)``."""
    if isinstance(value, ast.Name):
        return bound.get(value.id)
    module = _imported_module(value, key, param)
    if module is not None:
        return module_import(module, key)
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "getattr" \
            and len(value.args) == 2:
        module = _imported_module(value.args[0], key, param)
        attr = value.args[1]
        name = key if isinstance(attr, ast.Name) and attr.id == param else (
            attr.value if isinstance(attr, ast.Constant) and isinstance(attr.value, str) else None)
        if module is not None and name:
            return ImportInfo(module, name, key)
    return None


def _imported_module(call: ast.expr, key: str, param: str) -> str | None:
    """Return the module text of ``import_module("mod", ...)`` (``"." + name`` allowed), else ``None``."""
    if not (isinstance(call, ast.Call) and call.args):
        return None
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name != "import_module":
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add) and isinstance(arg.left, ast.Constant) \
            and isinstance(arg.right, ast.Name) and arg.right.id == param and isinstance(arg.left.value, str):
        return arg.left.value + key
    if isinstance(arg, ast.JoinedStr):
        text = "".join(
            str(v.value) if isinstance(v, ast.Constant) else _formatted(v, key, param) for v in arg.values
        )
        return text if "\0" not in text else None
    return None


def _formatted(node: ast.expr, key: str, param: str) -> str:
    """The text of one f-string field: *key* for the name parameter, ``""`` for ``__name__``; NUL when unknown."""
    if isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name):
        if node.value.id == param:
            return key
        if node.value.id in ("__name__", "__package__"):
            return ""
    return "\0"
