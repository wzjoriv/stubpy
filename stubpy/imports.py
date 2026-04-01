"""
stubpy.imports
==============

Import-statement analysis for ``.pyi`` header assembly.

Four functions cover the full import pipeline:

1. :func:`scan_import_statements` — parse source AST → ``{name: stmt}``
2. :func:`collect_typing_imports` — find used ``typing`` names in stub body
3. :func:`collect_cross_imports` — find cross-file class imports to re-emit
4. :func:`collect_special_imports` — detect ``abc`` / ``dataclasses`` needs
"""
from __future__ import annotations

import ast
import re
import types
from typing import Any


# ---------------------------------------------------------------------------
# Typing candidates — built dynamically from typing.__all__
# ---------------------------------------------------------------------------

# We build the set once at import time so it automatically includes any new
# names added in future Python releases.
try:
    import typing as _typing_mod
    _TYPING_CANDIDATES: frozenset[str] = frozenset(_typing_mod.__all__)
except Exception:
    # Fallback for unusual environments.
    _TYPING_CANDIDATES = frozenset({
        "Annotated", "Any", "Callable", "ClassVar", "Concatenate",
        "Dict", "Final", "FrozenSet", "Generic", "Iterator", "List",
        "Literal", "NamedTuple", "Optional", "ParamSpec", "Protocol",
        "Sequence", "Set", "Tuple", "Type", "TypeVar", "TypeVarTuple",
        "Union",
    })

_SKIP_IMPORT_PREFIXES: tuple[str, ...] = (
    "from typing",
    "from collections",
    "import typing",
    "from __future__",
    "from abc",
    "from dataclasses",
)


# ---------------------------------------------------------------------------
# Import scanning
# ---------------------------------------------------------------------------

def scan_import_statements(source: str) -> dict[str, str]:
    """Parse *source* and return a ``{local_name: import_statement}`` map.

    Walks the AST of *source* and builds one entry per imported name.
    Both ``from … import …`` and plain ``import …`` forms are supported,
    including ``as`` aliases. A single ``from`` statement importing
    multiple names produces one entry per name.

    ``from module import *`` produces a single entry under the special
    key ``"*"`` mapping to the original ``from module import *`` statement.
    Callers that need to pass through star-imports verbatim can check for
    this key explicitly.

    Parameters
    ----------
    source : str
        Raw Python source text to parse.

    Returns
    -------
    dict
        Maps each locally-bound name to its minimal import statement.
        Returns an empty dict on :exc:`SyntaxError`.

    Examples
    --------
    >>> result = scan_import_statements("from demo import types\\nimport os")
    >>> result["types"]
    'from demo import types'
    >>> result["os"]
    'import os'

    >>> result = scan_import_statements("from typing import Optional as Opt")
    >>> result["Opt"]
    'from typing import Optional as Opt'

    >>> result = scan_import_statements("from demo import *")
    >>> result["*"]
    'from demo import *'
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module_str = node.module or ""
            # Handle "from module import *"
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


# ---------------------------------------------------------------------------
# Typing import collection
# ---------------------------------------------------------------------------

def _extract_locally_defined_names(content: str) -> set[str]:
    """Return names that are defined locally in the stub body.

    Extracts class names (``class Foo``), function names (``def bar``),
    and parameter names (``x`` in ``def f(x: int)``).  These names are
    never typing imports even if they happen to match a name in
    ``typing.__all__``.

    Parameter names are found via the pattern ``[\(,]word:`` which catches
    positional and keyword parameters in function signatures without
    capturing base-class names from ``class Foo(Bar):`` forms.
    """
    local: set[str] = set()

    # Class names defined in the stub
    local.update(re.findall(r'\bclass\s+(\w+)', content))
    # Function / method names defined in the stub
    local.update(re.findall(r'\bdef\s+(\w+)', content))
    # Parameter names: word immediately followed by ':' in signature context
    # (preceded by '(' or ',').  Does NOT match 'class Foo(Bar):' because
    # there 'Bar' is followed by ')' not ':'.
    local.update(re.findall(r'(?:[\(,]\s*)(\w+)\s*:', content))

    return local


def collect_typing_imports(content: str) -> list[str]:
    """Return sorted :mod:`typing` names actually referenced in *content*.

    Dynamically scans :data:`typing.__all__` (computed once at module import
    time) rather than a fixed hard-coded list, so newly-added typing names are
    picked up automatically in future Python versions.

    Uses whole-word matching (``\\b`` word boundaries) to avoid false
    positives from substrings (e.g. ``List`` does not match inside
    ``BlackList``).

    Also excludes names that are *locally defined* in the stub body (class
    names, function names, parameter names) to avoid incorrectly importing
    ``typing.Container`` when the stub defines ``class Container`` or
    importing ``typing.override`` when a method has a parameter named
    ``override``.

    Parameters
    ----------
    content : str
        Generated stub body text (class and method stubs, without the
        header lines).

    Returns
    -------
    list of str
        Sorted list of :mod:`typing` names present in *content*.
        Empty list if none are used.

    Examples
    --------
    >>> collect_typing_imports("def foo(x: Optional[str]) -> None: ...")
    ['Optional']

    >>> collect_typing_imports("x: List[int], y: Dict[str, Any]")
    ['Any', 'Dict', 'List']

    >>> collect_typing_imports("def foo(x: int) -> None: ...")
    []

    >>> collect_typing_imports("class Container(Element): ...")
    []
    """
    locally_defined = _extract_locally_defined_names(content)
    candidates = _TYPING_CANDIDATES - locally_defined

    return sorted(
        name for name in candidates
        if re.search(rf"\b{re.escape(name)}\b", content)
    )


# ---------------------------------------------------------------------------
# Cross-file import collection
# ---------------------------------------------------------------------------

def collect_cross_imports(
    module: types.ModuleType,
    module_name: str,
    body: str,
    import_map: dict[str, str],
) -> list[str]:
    """Find cross-file imports that must be re-emitted in the ``.pyi`` header.

    Scans the stub *body* for two patterns:

    1. **Capitalised names** used as base classes or in type annotations
       (e.g. ``Element`` in ``class Container(Element):``).
    2. **Dotted module references** used in annotations
       (e.g. ``types`` in ``types.Length``). The module name (lowercase) is
       looked up in *import_map* so that ``from demo import types`` is
       re-emitted when variables carry ``types.Length`` annotations.

    Parameters
    ----------
    module : types.ModuleType
        The loaded source module, used to test whether a name is local.
    module_name : str
        Synthetic module name from :func:`~stubpy.loader.load_module`.
    body : str
        Already-generated stub class bodies (without the header lines).
    import_map : dict
        Result of :func:`scan_import_statements` for the source file.

    Returns
    -------
    list of str
        Deduplicated import statement strings safe to add verbatim to the
        ``.pyi`` header. Empty list if nothing needs importing.

    Examples
    --------
    >>> import types as _t
    >>> m = _t.ModuleType("mymod")
    >>> body = "class Container(Element):\\n    pass"
    >>> import_map = {"Element": "from demo.element import Element"}
    >>> collect_cross_imports(m, "mymod", body, import_map)
    ['from demo.element import Element']

    >>> body2 = "DEFAULT_WIDTH: types.Length"
    >>> import_map2 = {"types": "from demo import types"}
    >>> collect_cross_imports(m, "mymod", body2, import_map2)
    ['from demo import types']
    """
    needed_set: set[str] = set()
    needed: list[str] = []

    def _add(stmt: str) -> None:
        if stmt not in needed_set:
            needed_set.add(stmt)
            needed.append(stmt)

    # ── 1. Capitalised names in base classes and annotations ──────────────
    used_bases: set[str] = set()
    for group in re.findall(r"class \w+\(([^)]+)\)", body):
        for name in group.split(","):
            used_bases.add(name.strip())

    ann_names: set[str] = set(re.findall(r"(?::\s*|-> )([A-Z][A-Za-z0-9_]*)", body))

    for name in used_bases | ann_names:
        if name not in import_map:
            continue
        stmt = import_map[name]
        if any(stmt.startswith(p) for p in _SKIP_IMPORT_PREFIXES):
            continue
        obj = getattr(module, name, None)
        if obj is not None and getattr(obj, "__module__", None) == module_name:
            continue
        _add(stmt)

    # ── 2. Dotted module references: lowercase module before '.UpperName' ──
    # This catches annotation forms like `types.Length`, `types.Color` where
    # the module name is lowercase and would be missed by the pattern above.
    dotted_modules: set[str] = set(re.findall(r"\b([a-z_]\w*)(?=\.[A-Z])", body))

    for mod_name in dotted_modules:
        if mod_name not in import_map:
            continue
        stmt = import_map[mod_name]
        if any(stmt.startswith(p) for p in _SKIP_IMPORT_PREFIXES):
            continue
        _add(stmt)

    return needed


# ---------------------------------------------------------------------------
# Special import collection
# ---------------------------------------------------------------------------

def collect_special_imports(body: str) -> dict[str, list[str]]:
    """Return a ``{module: [names]}`` dict of extra imports needed in *body*.

    Checks for special constructs that require their own imports:

    - ``@abstractmethod`` or ``ABC`` base class → ``from abc import ...``
    - ``@dataclass`` → ``from dataclasses import dataclass``

    Parameters
    ----------
    body : str
        Generated stub body (class + function + variable stubs, no header).

    Returns
    -------
    dict
        Maps module name to a sorted list of names to import.

    Examples
    --------
    >>> collect_special_imports("@abstractmethod\\ndef foo(): ...")
    {'abc': ['abstractmethod']}
    >>> collect_special_imports("@dataclass\\nclass Foo: ...")
    {'dataclasses': ['dataclass']}
    >>> collect_special_imports("class Foo(ABC):\\n    pass")
    {'abc': ['ABC']}
    """
    result: dict[str, list[str]] = {}

    abc_needed: list[str] = []
    if "@abstractmethod" in body:
        abc_needed.append("abstractmethod")
    if re.search(r"\bABC\b", body):
        abc_needed.append("ABC")
    if abc_needed:
        result["abc"] = sorted(set(abc_needed))

    if re.search(r"@dataclass\b", body):
        result["dataclasses"] = ["dataclass"]

    return result
