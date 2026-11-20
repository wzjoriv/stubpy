"""
Named constants of parameter resolution: dataclass, attrs and partial forms, and typed stdlib callees.
"""
from __future__ import annotations

PARTIAL_NAMES: frozenset[str] = frozenset({"partial", "functools.partial"})

DATACLASS_DECORATORS: frozenset[str] = frozenset({"dataclass", "dataclasses.dataclass"})

ATTRS_AUTO_DECORATORS: frozenset[str] = frozenset({
    f"{prefix}{name}" for prefix in ("", "attr.", "attrs.") for name in ("define", "frozen", "mutable")
} | {"attr.dataclass", "attrs.dataclass"})

ATTRS_DECORATORS: frozenset[str] = ATTRS_AUTO_DECORATORS | frozenset({
    "attr.s", "attr.attrs", "attrs.attrs", "attrs", "attr.attributes", "attrs.attributes",
})

ATTRS_FIELD_CALLS: frozenset[str] = frozenset({
    "attr.ib", "attr.attrib", "attrs.attrib", "attr.field", "attrs.field", "attrib", "field",
})

ATTRS_FACTORY_TYPES: frozenset[str] = frozenset({"list", "dict", "set", "frozenset", "tuple", "str", "int", "float"})

NAMEDTUPLE_BASES: frozenset[str] = frozenset({"NamedTuple", "typing.NamedTuple"})

TYPEDDICT_BASES: frozenset[str] = frozenset({
    "TypedDict", "typing.TypedDict", "typing_extensions.TypedDict",
})

#: Typed signatures of stdlib callees whose live signature is missing, positional-only or untyped, by dotted name
STDLIB_SIGNATURES: dict[str, str] = {
    "io.open": (
        "def open(file, mode: str = 'r', buffering: int = -1, encoding: str | None = None, errors: str | None = None,"
        " newline: str | None = None, closefd: bool = True, opener: Callable[[str, int], int] | None = None): ..."
    ),
}

#: Modules that expose the same objects as the one a ``STDLIB_SIGNATURES`` key names
STDLIB_MODULE_ALIASES = {"builtins": "io", "_io": "io"}
