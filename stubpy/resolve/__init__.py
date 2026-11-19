"""
Parameter resolution: expand ``**kwargs`` / ``*args`` into the parameters they forward to.
"""
from ._local_scope import local_target
from ._merge import ParamWithHints, bind_partial
from .callables import (
    OwnedHints,
    class_hints_of,
    function_info_of,
    hints_of,
    introspection_cache,
    signature_of,
    source_tree_of,
    unwrap_callable,
)
from .hints import get_hints_for_method, get_own_annotations, get_raw_params, unwrap_descriptor
from .params import resolve_function_params, resolve_params

__all__ = [
    "OwnedHints",
    "ParamWithHints",
    "bind_partial",
    "class_hints_of",
    "function_info_of",
    "get_hints_for_method",
    "get_own_annotations",
    "get_raw_params",
    "hints_of",
    "introspection_cache",
    "local_target",
    "resolve_function_params",
    "resolve_params",
    "signature_of",
    "source_tree_of",
    "unwrap_callable",
    "unwrap_descriptor",
]
