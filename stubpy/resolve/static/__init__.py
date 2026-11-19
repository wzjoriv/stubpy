"""
Static ``**kwargs`` / ``*args`` back-tracing: classes, functions and imports read from source only.
"""
from ._attrs import AttrsField, attrs_fields
from ._lookup import ClassRef, FuncRef, PartialRef
from ._mro import static_mro
from ._raw import SourceHints, literal_default, own_params
from ._special import kind_of
from .index import SourceIndex, SourceModule, dotted_name
from .params import StaticResolver
from .unpack import unpacked_typeddict

__all__ = [
    "AttrsField",
    "ClassRef",
    "FuncRef",
    "PartialRef",
    "SourceHints",
    "SourceIndex",
    "SourceModule",
    "StaticResolver",
    "attrs_fields",
    "dotted_name",
    "kind_of",
    "literal_default",
    "own_params",
    "static_mro",
    "unpacked_typeddict",
]
