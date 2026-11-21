"""
Named constants of stub emission: decorator placement, separators, dunder types and default limits.
"""
from __future__ import annotations

KW_SEP_NAME = "__kw_sep__"

POS_SEP_NAME = "__pos_sep__"

IMPLICIT_CLASSMETHODS: frozenset[str] = frozenset({"__new__", "__init_subclass__", "__class_getitem__"})

MAX_DEFAULT_INT_BITS = 256

MAX_DEFAULT_LITERAL_LEN = 120

MAX_DEFAULT_CONTAINER_ITEMS = 8

FUNCTION_SOURCE_DECORATORS: frozenset[str] = frozenset({
    "deprecated", "contextmanager", "asynccontextmanager", "singledispatch",
})

METHOD_OUTER_DECORATORS: frozenset[str] = frozenset({"final", "override", "deprecated", "singledispatchmethod"})

METHOD_INNER_DECORATORS: frozenset[str] = frozenset({"contextmanager", "asynccontextmanager"})

ASYNC_ITERATOR_RETURN = "AsyncIterator[Any]"

PROPERTY_ACCESSOR_DECORATORS: frozenset[str] = frozenset({"setter", "deleter", "getter"})

DATACLASS_GENERATED_METHODS: frozenset[str] = frozenset({
    "__init__", "__repr__", "__eq__", "__ne__", "__hash__", "__lt__", "__le__", "__gt__", "__ge__",
    "__setattr__", "__delattr__", "__getstate__", "__setstate__", "__replace__",
})

#: Types of the positional parameters after the receiver of protocol dunders, written when unannotated
DUNDER_PARAMS: dict[str, tuple[str, ...]] = {"__eq__": ("object",), "__ne__": ("object",), "__format__": ("str",)}

#: The parameters (name, annotation) of a protocol dunder, for one whose signature cannot be read (a descriptor)
PROTOCOL_PARAMS: dict[str, tuple[tuple[str, str], ...]] = {
    **dict.fromkeys(("__getattr__", "__getattribute__", "__delattr__"), (("name", "str"),)),
    "__setattr__": (("name", "str"), ("value", "Any")),
    **dict.fromkeys(("__getitem__", "__delitem__"), (("key", "Any"),)),
    "__setitem__": (("key", "Any"), ("value", "Any")),
    "__contains__": (("item", "object"),),
    **dict.fromkeys(("__eq__", "__ne__"), (("other", "object"),)),
    **dict.fromkeys(("__lt__", "__le__", "__gt__", "__ge__", "__add__", "__sub__", "__mul__", "__truediv__",
                     "__floordiv__", "__mod__", "__pow__", "__and__", "__or__", "__xor__", "__lshift__", "__rshift__",
                     "__radd__", "__rsub__", "__rmul__", "__rtruediv__", "__rfloordiv__", "__rmod__", "__rpow__",
                     "__rand__", "__ror__", "__rxor__", "__iadd__", "__isub__", "__imul__", "__itruediv__"),
                    (("other", "Any"),)),
    "__call__": (("*args", "Any"), ("**kwargs", "Any")),
}

#: Deprecated ``typing`` aliases a stub writes under another name
TYPING_RENAMES: dict[str, str] = {
    "List": "list", "Dict": "dict", "Set": "set", "FrozenSet": "frozenset", "Tuple": "tuple", "Type": "type",
    "Text": "str", "DefaultDict": "defaultdict", "Deque": "deque", "AbstractSet": "Set",
    "ContextManager": "AbstractContextManager", "AsyncContextManager": "AbstractAsyncContextManager",
}

#: Annotation of a key read from ``**kwargs`` by the type of its literal ``.get`` default
READ_LITERAL_TYPES: dict[type, type] = {t: t for t in (bool, int, float, complex, str, bytes)}

#: Typing name a dispatch variant's selector is narrowed with
DISPATCH_LITERAL = "Literal"
