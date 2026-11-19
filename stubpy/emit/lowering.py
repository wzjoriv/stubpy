"""
PEP 695 type parameters rewritten as ``TypeVar`` declarations, so a version branch still parses on Python 3.10.
"""
from __future__ import annotations

import dataclasses
import re

from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.analysis.symbols.models import AliasSymbol, ClassSymbol, FunctionSymbol, OverloadGroup

__all__ = ["lower_symbol", "lower_type_params"]

_PARAM_RE = re.compile(r"^(\*{0,2})\s*([A-Za-z_]\w*)\s*(?::\s*(.+?))?\s*(?:=\s*(.+))?$")


def lower_type_params(params: list[str]) -> tuple[list[str], list[str]]:
    """Return the ``TypeVar`` declarations and generic arguments for PEP 695 type parameters.

    Parameters
    ----------
    params : list of str
        Type parameter source texts such as ``"T: int"``, ``"*Ts"`` or ``"**P"``.

    Returns
    -------
    declarations : list of str
        One ``Name = TypeVar(...)``-style declaration per parameter.
    arguments : list of str
        The names to subscript ``Generic`` with; a ``*Ts`` becomes ``Unpack[Ts]``.

    Examples
    --------
    >>> lower_type_params(["T: int", "*Ts", "**P"])
    (['T = TypeVar("T", bound=int)', 'Ts = TypeVarTuple("Ts")', 'P = ParamSpec("P")'], ['T', 'Unpack[Ts]', 'P'])
    >>> lower_type_params(["S: (int, str)"])[0]
    ['S = TypeVar("S", int, str)']
    """
    decls: list[str] = []
    args: list[str] = []
    for text in params:
        m = _PARAM_RE.match(text.strip())
        if m is None:
            continue
        stars, name, bound, default = m.groups()
        extra = ""
        if stars == "**":
            kind = "ParamSpec"
        elif stars == "*":
            kind = "TypeVarTuple"
        else:
            kind = "TypeVar"
            if bound and bound.startswith("(") and bound.endswith(")"):
                extra = f", {bound[1:-1].strip().rstrip(',')}"
            elif bound:
                extra = f", bound={bound}"
        if default:
            extra += f", default={default}"
        decls.append(f'{name} = {kind}("{name}"{extra})')
        args.append(f"Unpack[{name}]" if stars == "*" else name)
    return decls, args


def _lower_function(info: FunctionInfo, decls: list[str]) -> FunctionInfo:
    if not info.type_params:
        return info
    decls.extend(lower_type_params(info.type_params)[0])
    return dataclasses.replace(info, type_params=[])


def _lower_class(info: ClassInfo, decls: list[str], whole: bool) -> ClassInfo:
    """Lower *info*'s own parameters when *whole*, and those of its branched (or, when *whole*, all) members."""
    changes: dict = {}
    if whole and info.type_params:
        own, args = lower_type_params(info.type_params)
        decls.extend(own)
        changes = {"type_params": [], "bases": [*info.bases, f"Generic[{', '.join(args)}]"]}
    methods = [_lower_function(m, decls) if whole or m.branch else m for m in info.methods]
    classes = [_lower_class(c, decls, whole or bool(c.branch)) for c in info.classes]
    return dataclasses.replace(info, methods=methods, classes=classes, **changes)


def lower_symbol(sym: object) -> list[str]:
    """Rewrite the PEP 695 parameters of a symbol inside version branches, in place.

    A symbol in a branch is lowered whole; an unconditional class only has
    its branched members lowered. ``type X = ...`` aliases outside a branch
    are written by the alias emitter instead.

    Parameters
    ----------
    sym : object
        A function, overload group, class or alias symbol.

    Returns
    -------
    list of str
        The distinct ``TypeVar`` declarations the lowered symbol needs.

    See Also
    --------
    lower_type_params : Builds the declarations for one parameter list.

    Examples
    --------
    >>> lower_symbol(object())
    []
    """
    branched = bool(getattr(sym, "branch", ()))
    decls: list[str] = []
    if isinstance(sym, FunctionSymbol) and branched and sym.ast_info is not None:
        sym.ast_info = _lower_function(sym.ast_info, decls)
    elif isinstance(sym, OverloadGroup) and branched:
        for variant in sym.variants:
            if variant.ast_info is not None:
                variant.ast_info = _lower_function(variant.ast_info, decls)
    elif isinstance(sym, ClassSymbol) and sym.ast_info is not None:
        sym.ast_info = _lower_class(sym.ast_info, decls, branched)
    elif isinstance(sym, AliasSymbol) and branched and sym.ast_info is not None and sym.ast_info.type_params:
        decls.extend(lower_type_params(sym.ast_info.type_params)[0])
        sym.ast_info = dataclasses.replace(sym.ast_info, type_params=[])
    return list(dict.fromkeys(decls))
