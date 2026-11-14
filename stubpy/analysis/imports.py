"""Import analysis: scan source imports and collect the imports a stub body needs."""
from __future__ import annotations

import ast
import re
import types

from stubpy._constants import DECORATOR_MODULES, STUB_DECORATORS, TYPING_CANDIDATES

from .astutil import iter_statements

_SKIP_IMPORT_PREFIXES: tuple[str, ...] = (
    "from typing",
    "from collections",
    "import typing",
    "from __future__",
    "from abc",
    "from dataclasses",
    "from enum",
    "import enum",
)


_WORD_RE = re.compile(r"\b[A-Za-z_]\w*\b")
_CAPITALISED_RE = re.compile(r"(?<![\w.])([A-Z]\w*)")
_DECORATOR_RE = re.compile(r"^\s*@(\w+)", re.MULTILINE)


def scan_import_statements(source: str | ast.Module) -> dict[str, str]:
    """Return ``{local_name: import_statement}`` for every import in *source*.

    *source* is source text or an already parsed module.  Relative imports
    keep their dots.  ``from m import *`` is stored under the key ``"*"``.
    Returns ``{}`` on :exc:`SyntaxError`.

    Examples
    --------
    >>> scan_import_statements("from demo import types\\nimport os")
    {'types': 'from demo import types', 'os': 'import os'}
    >>> scan_import_statements("from . import sub")
    {'sub': 'from . import sub'}
    """
    if isinstance(source, ast.Module):
        tree = source
    else:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}

    imports: dict[str, str] = {}
    for node in iter_statements(tree):
        if isinstance(node, ast.ImportFrom):
            module_str = "." * node.level + (node.module or "")
            if len(node.names) == 1 and node.names[0].name == "*":
                imports["*"] = f"from {module_str} import *"
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                stmt = f"from {module_str} import {alias.name}"
                if alias.asname:
                    stmt += f" as {alias.asname}"
                imports[local] = stmt
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[-1]
                stmt = f"import {alias.name}"
                if alias.asname:
                    stmt += f" as {alias.asname}"
                imports[local] = stmt

    return imports


def _extract_locally_defined_names(content: str) -> set[str]:
    """Return class, function and parameter names defined in the stub body."""
    local: set[str] = set()
    local.update(re.findall(r'\bclass\s+(\w+)', content))
    local.update(re.findall(r'\bdef\s+(\w+)', content))
    local.update(re.findall(r'(?:[\(,]\s*)(\w+)\s*:', content))
    local.update(re.findall(r'^(\w+)\s*[:=]', content, re.MULTILINE))
    return local


def collect_typing_imports(content: str) -> list[str]:
    """Return the sorted :mod:`typing` names referenced in a stub body.

    Matches whole words only and ignores names the stub defines itself.

    Examples
    --------
    >>> collect_typing_imports("x: List[int], y: Dict[str, Any]")
    ['Any', 'Dict', 'List']
    >>> collect_typing_imports("class Container(Element): ...")
    []
    """
    words = set(_WORD_RE.findall(content))
    candidates = (TYPING_CANDIDATES & words) - _extract_locally_defined_names(content)
    return sorted(candidates)


def collect_decorator_imports(body: str) -> dict[str, list[str]]:
    """Return ``{module: names}`` for the stub decorators used in *body* that need an import.

    Examples
    --------
    >>> collect_decorator_imports("@cached_property\\ndef x(self) -> int: ...")
    {'functools': ['cached_property']}
    """
    result: dict[str, set[str]] = {}
    for name in set(_DECORATOR_RE.findall(body)):
        if name not in STUB_DECORATORS or name in ("property", "classmethod", "staticmethod"):
            continue
        module = DECORATOR_MODULES.get(name) or (
            "typing" if name in TYPING_CANDIDATES else "typing_extensions"
        )
        result.setdefault(module, set()).add(name)
    return {m: sorted(names) for m, names in sorted(result.items())}


def collect_cross_imports(
    module: types.ModuleType,
    module_name: str,
    body: str,
    import_map: dict[str, str],
) -> list[str]:
    """Return the source imports a stub body must re-emit, deduplicated in order.

    Covers capitalised names used anywhere in the body (unless defined in
    *module_name* itself) and lowercase modules used as ``mod.Name``.

    Examples
    --------
    >>> import types as _t
    >>> m = _t.ModuleType("mymod")
    >>> collect_cross_imports(m, "mymod", "class Container(Element):\\n    pass",
    ...                       {"Element": "from demo.element import Element"})
    ['from demo.element import Element']
    """
    needed_set: set[str] = set()
    needed: list[str] = []

    def _add(stmt: str) -> None:
        if stmt not in needed_set:
            needed_set.add(stmt)
            needed.append(stmt)

    used_bases: set[str] = set()
    for group in re.findall(r"class \w+\(([^)]+)\)", body):
        for name in group.split(","):
            used_bases.add(name.strip())

    ann_names: set[str] = set(_CAPITALISED_RE.findall(body))

    defined_here = _extract_locally_defined_names(body)
    for name in used_bases | ann_names:
        if name not in import_map or name in defined_here:
            continue
        stmt = import_map[name]
        if any(stmt.startswith(p) for p in _SKIP_IMPORT_PREFIXES):
            continue
        obj = getattr(module, name, None)
        if obj is not None and getattr(obj, "__module__", None) == module_name:
            continue
        _add(stmt)

    dotted_modules: set[str] = set(re.findall(r"\b([a-z_]\w*)(?=\.[A-Z])", body))

    for mod_name in sorted(dotted_modules):
        if mod_name not in import_map:
            continue
        stmt = import_map[mod_name]
        if stmt.startswith("from __future__"):
            continue
        _add(stmt)

    return needed


def collect_special_imports(body: str) -> dict[str, list[str]]:
    """Return the ``abc`` / ``dataclasses`` / ``enum`` names a stub body needs.

    Examples
    --------
    >>> collect_special_imports("@abstractmethod\\ndef foo(): ...")
    {'abc': ['abstractmethod']}
    >>> collect_special_imports("@dataclass\\nclass Foo: ...")
    {'dataclasses': ['dataclass']}
    """
    result: dict[str, list[str]] = {}

    abc_needed: list[str] = []
    if "@abstractmethod" in body:
        abc_needed.append("abstractmethod")
    if re.search(r"\bABC\b", body):
        abc_needed.append("ABC")
    if abc_needed:
        result["abc"] = sorted(set(abc_needed))

    dataclass_names = [n for n, pattern in (("InitVar", r"\bInitVar\["), ("KW_ONLY", r":\s*KW_ONLY\b"))
                       if re.search(pattern, body)]
    if re.search(r"@dataclass\b", body):
        dataclass_names.append("dataclass")
    if dataclass_names:
        result["dataclasses"] = sorted(dataclass_names)

    enum_names = []
    for name in ("Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"):
        if re.search(rf"\b{name}\b", body):
            enum_names.append(name)
    if enum_names:
        result["enum"] = sorted(enum_names)

    return result
