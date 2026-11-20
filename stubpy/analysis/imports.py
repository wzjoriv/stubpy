"""
Import analysis: scan source imports and collect the imports a stub body needs.
"""
from __future__ import annotations

import ast
import re
import types

from stubpy._constants import MODERN_HOMES, STUB_DECORATORS, TYPING_BACKPORTS, TYPING_CANDIDATES
from stubpy.analysis._constants import DECORATOR_MODULES

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
_BARE_WORD_RE = re.compile(r"(?<![\w.])[A-Za-z_]\w*\b")
_CAPITALISED_RE = re.compile(r"(?<![\w.])([A-Z]\w*)")
_REFERENCE_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\b(?!\s*:(?!=)|\s*=(?!=)|\.)")
_STRING_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|\'[^\'\n]*\'|"[^"\n]*"')
_DECORATOR_RE = re.compile(r"^\s*@(\w+)", re.MULTILINE)


def scan_import_statements(source: str | ast.Module) -> dict[str, str]:
    """Return ``{local_name: import_statement}`` for every import in *source*.

    Relative imports keep their dots.  ``from m import *`` is stored under the key ``"*"``.

    Parameters
    ----------
    source : str or ast.Module
        Source text or an already parsed module.

    Returns
    -------
    dict of str to str
        Local name to import statement; empty on :exc:`SyntaxError`.

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


def defined_names(content: str) -> set[str]:
    """Return class, function and parameter names defined in the stub body.

    Parameters
    ----------
    content : str
        Stub text.

    Returns
    -------
    set of str
        Names introduced by ``class``, ``def``, parameters and top-level annotations or assignments.

    Examples
    --------
    >>> sorted(defined_names("class A: ...\\ndef f(x: int): ..."))
    ['A', 'f', 'x']
    """
    local: set[str] = set()
    local.update(re.findall(r'\bclass\s+(\w+)', content))
    local.update(re.findall(r'\bdef\s+(\w+)', content))
    local.update(re.findall(r'(?:[\(,]\s*)(\w+)\s*:', content))
    local.update(re.findall(r'^(\w+)\s*[:=]', content, re.MULTILINE))
    return local


def collect_typing_imports(content: str) -> list[str]:
    """Return the sorted :mod:`typing` names referenced in a stub body.

    Matches whole words only and ignores names the stub defines itself.

    Parameters
    ----------
    content : str
        Stub text.

    Returns
    -------
    list of str
        Sorted names to import from :mod:`typing`.

    Examples
    --------
    >>> collect_typing_imports("x: List[int], y: Dict[str, Any]")
    ['Any', 'Dict', 'List']
    >>> collect_typing_imports("class Container(Element): ...")
    []
    """
    words = set(_WORD_RE.findall(_STRING_RE.sub("''", content)))
    candidates = (TYPING_CANDIDATES & words) - defined_names(content) - MODERN_HOMES.keys()
    return sorted(candidates)


def collect_decorator_imports(body: str) -> dict[str, list[str]]:
    """Return ``{module: names}`` for the stub decorators used in *body* that need an import.

    Parameters
    ----------
    body : str
        Stub text.

    Returns
    -------
    dict of str to list of str
        Module name to the sorted decorator names to import from it.

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

    Covers names used anywhere in the body outside string literals,
    parameter names and keyword defaults (unless defined in *module_name*
    itself), and lowercase modules used as ``mod.Name``.

    Parameters
    ----------
    module : types.ModuleType
        The loaded module, used to skip names it defines itself.
    module_name : str
        The module's ``__name__``.
    body : str
        Stub text.
    import_map : dict of str to str
        Local name to import statement, as from :func:`scan_import_statements`.

    Returns
    -------
    list of str
        Import statements, in first-use order.

    See Also
    --------
    scan_import_statements : Builds the *import_map*.

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

    ann_names: set[str] = set(_CAPITALISED_RE.findall(body)) | set(_REFERENCE_RE.findall(_STRING_RE.sub("", body)))

    defined_here = defined_names(body)
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

    dotted_modules: set[str] = set(re.findall(r"(?<![\w.])([a-z_]\w*)(?=\.\w)", body))

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

    Also covers ``functools.partial`` and the :mod:`typing_extensions` backports.

    Parameters
    ----------
    body : str
        Stub text.

    Returns
    -------
    dict of str to list of str
        Module name to the sorted names to import from it.

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
    if re.search(r"(?<![\w.])ABC\b", body):
        abc_needed.append("ABC")
    if abc_needed:
        result["abc"] = sorted(set(abc_needed))

    dataclass_names = [n for n, pattern in (("InitVar", r"\bInitVar\["), ("KW_ONLY", r":\s*KW_ONLY\b"))
                       if re.search(pattern, body)]
    if re.search(r"@dataclass\b", body):
        dataclass_names.append("dataclass")
    if dataclass_names:
        result["dataclasses"] = sorted(dataclass_names)

    if re.search(r"(?<![\w.])partial\[", body):
        result["functools"] = ["partial"]

    enum_names = []
    for name in ("Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"):
        if re.search(rf"(?<![\w.]){name}\b", body):
            enum_names.append(name)
    if enum_names:
        result["enum"] = sorted(enum_names)

    backports = sorted((TYPING_BACKPORTS & set(_WORD_RE.findall(body))) - defined_names(body))
    if backports:
        result["typing_extensions"] = backports

    return result


def collect_modern_imports(body: str) -> dict[str, list[str]]:
    """Return ``{module: names}`` for the modern homes of the names :func:`~stubpy.emit.modern.modernize` writes.

    Parameters
    ----------
    body : str
        Stub text.

    Returns
    -------
    dict of str to list of str
        Module name to the sorted names to import from it.

    Examples
    --------
    >>> collect_modern_imports("def f(cb: Callable[[], None], m: Pattern[str]) -> deque[int]: ...")
    {'collections': ['deque'], 'collections.abc': ['Callable'], 're': ['Pattern']}
    """
    words = set(_BARE_WORD_RE.findall(_STRING_RE.sub("''", body))) - defined_names(body)
    result: dict[str, set[str]] = {}
    for name in words & MODERN_HOMES.keys():
        result.setdefault(MODERN_HOMES[name], set()).add(name)
    return {m: sorted(names) for m, names in sorted(result.items())}
