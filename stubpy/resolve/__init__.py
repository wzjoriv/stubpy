"""Parameter resolution: expand ``**kwargs`` / ``*args`` into the parameters they forward to."""
from ._merge import ParamWithHints
from .hints import get_hints_for_method, get_own_annotations, get_raw_params, unwrap_descriptor
from .params import resolve_function_params, resolve_params

__all__ = [
    "ParamWithHints",
    "get_hints_for_method",
    "get_own_annotations",
    "get_raw_params",
    "resolve_function_params",
    "resolve_params",
    "unwrap_descriptor",
]
