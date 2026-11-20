"""
Parameters of a function known only from source: harvested raw parameters to ``inspect.Parameter`` pairs.
"""
from __future__ import annotations

import inspect
from typing import Any

from stubpy.analysis.harvest.models import RawParam
from stubpy.resolve import ParamWithHints
from stubpy.resolve.static import literal_default

_KINDS = {
    "POSITIONAL_ONLY": inspect.Parameter.POSITIONAL_ONLY,
    "POSITIONAL_OR_KEYWORD": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "VAR_POSITIONAL": inspect.Parameter.VAR_POSITIONAL,
    "KEYWORD_ONLY": inspect.Parameter.KEYWORD_ONLY,
    "VAR_KEYWORD": inspect.Parameter.VAR_KEYWORD,
}


def params_from_raw(raw_params: list[RawParam], skip_receiver_names: bool = True) -> list[ParamWithHints]:
    """Build ``inspect.Parameter`` objects from harvested parameters.

    ``self`` / ``cls`` are skipped unless *skip_receiver_names* is false.
    Literal defaults are evaluated; other defaults become
    :class:`NonLiteralDefault`. An explicit annotation wins over one
    inferred from the default.

    Parameters
    ----------
    raw_params : list of RawParam
        The harvested parameters.
    skip_receiver_names : bool, optional
        Whether to drop parameters named ``self`` or ``cls``. Defaults to True.

    Returns
    -------
    list of tuple
        ``(inspect.Parameter, {})`` pairs.

    See Also
    --------
    build_ast_only_params : Builds the pairs from a function's AST info.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> method = ast_harvest("class A:\\n    def f(self, x: int = 3): ...").classes[0].methods[0]
    >>> [(p.name, p.default) for p, _ in params_from_raw(method.raw_params)]
    [('x', 3)]
    """
    result: list[ParamWithHints] = []
    for rp in raw_params:
        if skip_receiver_names and rp.name in ("self", "cls"):
            continue
        kind = _KINDS.get(rp.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        default: Any = inspect.Parameter.empty
        if rp.default_repr is not None:
            default = literal_default(rp.default_repr)
        annotation: Any = inspect.Parameter.empty
        if rp.annotation_str:
            annotation = rp.annotation_str
        elif rp.inferred_type_str:
            annotation = rp.inferred_type_str
        result.append((inspect.Parameter(rp.name, kind, default=default, annotation=annotation), {}))
    return result


def build_ast_only_params(ast_info: Any | None) -> list[ParamWithHints]:
    """Reconstruct a function's parameters from AST data alone.

    Uses ``raw_params`` when present, otherwise falls back to the
    unordered ``raw_arg_annotations`` mapping.

    Parameters
    ----------
    ast_info : FunctionInfo or None
        The function's AST info.

    Returns
    -------
    list of tuple
        ``(inspect.Parameter, {})`` pairs; empty without AST info.

    See Also
    --------
    params_from_raw : Converts harvested parameters.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> info = SimpleNamespace(raw_arg_annotations={"self": "", "x": "int", "*rest": "str"})
    >>> [p.name for p, _ in build_ast_only_params(info)]
    ['x', 'rest']
    >>> build_ast_only_params(None)
    []
    """
    if ast_info is None:
        return []

    raw_params = getattr(ast_info, "raw_params", None)
    if raw_params:
        return params_from_raw(raw_params)

    raw_anns: dict[str, str] = getattr(ast_info, "raw_arg_annotations", {})
    params: list[ParamWithHints] = []
    seen: set[str] = set()
    for raw_name, ann_str in raw_anns.items():
        if raw_name.startswith("**"):
            kind = inspect.Parameter.VAR_KEYWORD
            name = raw_name[2:]
        elif raw_name.startswith("*"):
            kind = inspect.Parameter.VAR_POSITIONAL
            name = raw_name[1:]
        else:
            kind = inspect.Parameter.POSITIONAL_OR_KEYWORD
            name = raw_name
        if name in ("self", "cls") or name in seen:
            continue
        seen.add(name)
        params.append((inspect.Parameter(name, kind, annotation=ann_str), {}))
    return params
