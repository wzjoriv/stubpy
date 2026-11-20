"""
Named constants of source analysis: hint decorators, module dunders, newer syntax and known type names.
"""
from __future__ import annotations

import typing

TYPING_TYPE_NAMES: frozenset[str] = frozenset(
    n for n in typing.__all__ if not n.startswith("_") and n[0].isupper()
)

BUILTIN_TYPE_NAMES: frozenset[str] = frozenset({
    "int", "float", "complex", "bool", "str", "bytes", "bytearray",
    "list", "tuple", "set", "frozenset", "dict", "type", "object",
    "memoryview", "range", "slice",
})

KNOWN_TYPE_NAMES: frozenset[str] = BUILTIN_TYPE_NAMES | TYPING_TYPE_NAMES

SOURCE_ROOT_NAMES: frozenset[str] = frozenset({"src", "lib", "source"})

DECORATOR_MODULES: dict[str, str] = {
    "abstractmethod": "abc",
    "abstractproperty": "abc",
    "cached_property": "functools",
    "dataclass": "dataclasses",
    "deprecated": "typing_extensions",
    "contextmanager": "contextlib",
    "asynccontextmanager": "contextlib",
    "singledispatch": "functools",
    "singledispatchmethod": "functools",
}

MODULE_DUNDER_TYPES: dict[str, str] = {
    "__version__": "str",
    "__author__": "str",
    "__email__": "str",
    "__license__": "str",
    "__copyright__": "str",
}

HIDDEN_MODULE_DUNDERS: frozenset[str] = frozenset({"__all__", "__slots__", "__doc__", "__file__", "__path__"})

HINT_MODULE = "stubpy.hint"

HINT_DECORATORS: frozenset[str] = frozenset({"signature", "returns", "ignore"})

HINT_DEFAULT_PREFIXES: frozenset[str] = frozenset({"stubpy.hint", "hint"})

COPY_FUNCTIONS = {"dataclasses": "replace", "copy": "replace", "attrs": "evolve", "attr": "evolve"}

#: Syntax a Python release added: a source that fails to parse and matches one needs that release
NEWER_SYNTAX: tuple[tuple[tuple[int, int], str, str], ...] = (
    ((3, 14), r"^\s*except\*?\s+[^\s(:][^:]*,[^:]*:", "unparenthesized 'except A, B:'"),
    ((3, 14), r"(?<![\w'\"])[tT][rR]?(?:'|\")", "template string"),
    ((3, 12), r"^\s*type\s+[A-Za-z_]\w*\s*[\[=]", "'type' alias statement"),
    ((3, 12), r"^\s*(?:async\s+)?(?:def|class)\s+[A-Za-z_]\w*\s*\[", "type parameter list"),
    ((3, 11), r"^\s*except\s*\*", "'except*'"),
)

STATEMENT_BLOCK_FIELDS = ("body", "handlers", "orelse", "finalbody", "cases")

#: Builtin calls whose result type never depends on the argument, for return inference
TYPED_BUILTIN_CALLS: dict[str, str] = {
    "str": "str", "repr": "str", "ascii": "str", "format": "str", "chr": "str", "hex": "str", "oct": "str",
    "bin": "str", "len": "int", "ord": "int", "hash": "int", "id": "int", "int": "int", "float": "float",
    "bytes": "bytes", "bool": "bool", "isinstance": "bool", "issubclass": "bool", "callable": "bool",
    "hasattr": "bool",
}

#: ``str`` methods by result type, applied when the receiver is a string literal or f-string
STR_METHOD_RESULTS: dict[str, str] = {
    **dict.fromkeys((
        "capitalize", "casefold", "center", "expandtabs", "format", "format_map", "join", "ljust", "lower",
        "lstrip", "removeprefix", "removesuffix", "replace", "rjust", "rstrip", "strip", "swapcase", "title",
        "upper", "zfill",
    ), "str"),
    **dict.fromkeys(("count", "find", "index", "rfind", "rindex"), "int"),
    **dict.fromkeys((
        "endswith", "isalnum", "isalpha", "isascii", "isdecimal", "isdigit", "isidentifier", "islower",
        "isnumeric", "isprintable", "isspace", "istitle", "isupper", "startswith",
    ), "bool"),
}

#: Decorators that keep a function's return type, so an inferred return still applies
RETURN_KEEPING_DECORATORS: frozenset[str] = frozenset({
    "staticmethod", "classmethod", "property", "setter", "deleter", "cached_property", "cache", "lru_cache",
    "override", "final",
})
