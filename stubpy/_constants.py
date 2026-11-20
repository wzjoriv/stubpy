"""
Named constants shared across stubpy's sub-packages.
The ``inspect.Parameter`` kinds load on first access, so ``from stubpy import hint`` stays cheap.
"""
from __future__ import annotations

import typing
from typing import Any

TARGET_MODULE_PREFIX = "_stubpy_target_"
BEGIN_MARKER = "# stubpy: auto-generated begin"
END_MARKER = "# stubpy: auto-generated end"

_PARAMETER_KINDS: dict[str, str] = {
    "POS_ONLY": "POSITIONAL_ONLY",
    "POS_KW": "POSITIONAL_OR_KEYWORD",
    "VAR_POS": "VAR_POSITIONAL",
    "KW_ONLY": "KEYWORD_ONLY",
    "VAR_KW": "VAR_KEYWORD",
}


def __getattr__(name: str) -> Any:
    """Resolve the ``inspect.Parameter`` kind constants lazily."""
    if name in _PARAMETER_KINDS:
        import inspect

        value = getattr(inspect.Parameter, _PARAMETER_KINDS[name])
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

TYPING_CANDIDATES: frozenset[str] = frozenset(typing.__all__)

TYPING_BACKPORTS: frozenset[str] = frozenset({
    "Self", "LiteralString", "Never", "TypeVarTuple", "Unpack", "Required", "NotRequired",
    "TypeIs", "ReadOnly", "TypeAliasType", "assert_never", "assert_type", "reveal_type",
    "dataclass_transform", "override", "get_overloads", "clear_overloads", "NoDefault",
}) - TYPING_CANDIDATES

UNINFORMATIVE_DEFAULT_TYPES: frozenset[str] = frozenset({
    "object", "type", "function", "method", "builtin_function_or_method", "module",
})

UNINFORMATIVE_VALUE_TYPES: frozenset[str] = UNINFORMATIVE_DEFAULT_TYPES | {"NoneType"}

PUBLIC_DUNDERS: frozenset[str] = frozenset({
    "__init__", "__new__", "__call__", "__init_subclass__", "__class_getitem__",
    "__repr__", "__str__", "__bytes__", "__format__", "__hash__", "__bool__",
    "__len__", "__length_hint__", "__getitem__", "__setitem__", "__delitem__", "__missing__",
    "__contains__", "__iter__", "__next__", "__reversed__",
    "__enter__", "__exit__", "__aenter__", "__aexit__", "__aiter__", "__anext__", "__await__",
    "__get__", "__set__", "__delete__", "__set_name__",
    "__getattr__", "__setattr__", "__delattr__", "__dir__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__",
    "__add__", "__radd__", "__iadd__", "__sub__", "__rsub__", "__isub__",
    "__mul__", "__rmul__", "__imul__", "__matmul__", "__rmatmul__", "__imatmul__",
    "__truediv__", "__rtruediv__", "__itruediv__", "__floordiv__", "__rfloordiv__", "__ifloordiv__",
    "__mod__", "__rmod__", "__imod__", "__divmod__", "__rdivmod__", "__pow__", "__rpow__", "__ipow__",
    "__lshift__", "__rlshift__", "__ilshift__", "__rshift__", "__rrshift__", "__irshift__",
    "__and__", "__rand__", "__iand__", "__or__", "__ror__", "__ior__", "__xor__", "__rxor__", "__ixor__",
    "__neg__", "__pos__", "__abs__", "__invert__",
    "__int__", "__float__", "__complex__", "__index__", "__round__", "__trunc__", "__floor__", "__ceil__",
    "__fspath__", "__buffer__", "__release_buffer__",
    "__deepcopy__", "__copy__", "__post_init__",
})

STUB_DECORATORS: frozenset[str] = frozenset({
    "overload", "abstractmethod", "property", "cached_property",
    "classmethod", "staticmethod", "final", "override",
    "dataclass_transform", "deprecated", "runtime_checkable", "type_check_only",
    "dataclass", "abstractproperty",
    "contextmanager", "asynccontextmanager", "singledispatch", "singledispatchmethod",
})

ENUM_BASE_NAMES: frozenset[str] = frozenset({
    "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum",
})

STUB_SUFFIX = ".pyi"
SOURCE_SUFFIX = ".py"

HINT_SIGNATURE_ATTR = "__stubpy_signature__"
HINT_RETURNS_ATTR = "__stubpy_returns__"
HINT_IGNORE_ATTR = "__stubpy_ignore__"
#: Return types of protocol dunders, written when the method has none
DUNDER_RETURNS: dict[str, str] = {
    "__init__": "None", "__init_subclass__": "None", "__repr__": "str", "__str__": "str", "__format__": "str", "__bytes__": "bytes",
    "__hash__": "int", "__len__": "int", "__int__": "int", "__index__": "int", "__float__": "float",
    "__complex__": "complex", "__bool__": "bool", "__contains__": "bool", "__eq__": "bool", "__ne__": "bool",
    "__lt__": "bool", "__le__": "bool", "__gt__": "bool", "__ge__": "bool", "__setitem__": "None",
    "__delitem__": "None", "__setattr__": "None", "__delattr__": "None",
}
_ABC_NAMES = (
    "Callable", "Iterator", "Iterable", "Generator", "AsyncIterator", "AsyncIterable", "AsyncGenerator",
    "Awaitable", "Coroutine", "Mapping", "MutableMapping", "Sequence", "MutableSequence", "MutableSet",
    "Collection", "Container", "Hashable", "Sized", "Reversible", "KeysView", "ItemsView", "ValuesView",
    "MappingView",
)
#: Deprecated ``typing`` aliases kept by name, imported from their real home instead
TYPING_MOVED: frozenset[str] = frozenset(_ABC_NAMES) | {
    "Pattern", "Match", "OrderedDict", "Counter", "ChainMap",
}
#: Where a stub imports each modern name from (``Set`` only appears as the rename of ``AbstractSet``)
MODERN_HOMES: dict[str, str] = {
    **dict.fromkeys(_ABC_NAMES, "collections.abc"), "Set": "collections.abc",
    "Pattern": "re", "Match": "re",
    "OrderedDict": "collections", "Counter": "collections", "ChainMap": "collections",
    "defaultdict": "collections", "deque": "collections",
    "AbstractContextManager": "contextlib", "AbstractAsyncContextManager": "contextlib",
}

#: Call target that stands for "every field of this class" (``dataclasses.replace(obj, **changes)``)
FIELDS_PREFIX = "<fields>:"
#: The ``exclude`` rule for folders and module files whose names Python cannot import
NON_IDENTIFIER_RULE = "<non-identifier>"

#: ``exclude`` when it is not set: hidden and tool folders, build output, unimportable names
DEFAULT_EXCLUDE: tuple[str, ...] = (
    ".*", "__pycache__", "build", "dist", ".venv", "venv", "*.egg-info", ".git", ".tox", ".nox", NON_IDENTIFIER_RULE,
)

#: Marker for an inferred ``return self`` / ``return cls(...)``; emitted as ``Self`` or the class name
SELF_RETURN = "Self"
