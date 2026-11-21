"""
TypeVar, TypeAlias, NewType, ParamSpec and TypeVarTuple declaration stubs.
"""
from __future__ import annotations

import ast
import sys

from stubpy.analysis.symbols.models import AliasSymbol
from stubpy.state.context import StubContext

from .annotations.style import style_text


def resolve_alias_style(ctx: StubContext) -> str:
    """Return the effective alias style, ``"pep695"`` or ``"compatible"``.

    Reads ``alias_style`` from the config; ``"auto"`` picks ``"pep695"`` on
    Python 3.12 and later, and unknown values fall back to ``"compatible"``.

    Parameters
    ----------
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        ``"pep695"`` or ``"compatible"``.

    See Also
    --------
    generate_alias_stub : Uses the style to write a type alias.

    Examples
    --------
    >>> resolve_alias_style(StubContext()) == "compatible"
    True
    """
    style = getattr(ctx.config, "alias_style", "compatible")
    if style == "auto":
        return "pep695" if sys.version_info >= (3, 12) else "compatible"
    return style if style in ("pep695", "compatible") else "compatible"


def generate_alias_stub(sym: AliasSymbol, ctx: StubContext) -> str:
    """Re-emit a type alias or TypeVar-style declaration from its source text.

    Type aliases follow ``alias_style``: ``Name: TypeAlias = rhs``
    (compatible) or ``type Name = rhs`` (pep695); a generic PEP 695 alias
    (``type Pair[T] = ...``) keeps its own syntax, which its source already needs.
    Inside a version branch the compatible form is always used, so the stub
    parses on older Pythons. TypeVar, ParamSpec, TypeVarTuple and NewType
    always emit ``Name = Kind(...)``.

    Parameters
    ----------
    sym : AliasSymbol
        The alias symbol.
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        One declaration line, or ``""`` without AST data.

    See Also
    --------
    resolve_alias_style : Picks the alias style.

    Examples
    --------
    >>> from stubpy.analysis.harvest import TypeVarInfo
    >>> tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
    >>> generate_alias_stub(AliasSymbol("T", lineno=1, ast_info=tv), StubContext())
    "T = TypeVar('T')"
    """
    ai = sym.ast_info
    if ai is None:
        return ""

    if ai.kind == "TypeAlias":
        rhs = style_text(ai.source_str, ctx)
        if ai.type_params:
            return f"type {sym.name}[{', '.join(ai.type_params)}] = {rhs}"
        if resolve_alias_style(ctx) == "pep695" and not sym.branch:
            return f"type {sym.name} = {rhs}" if rhs else f"type {sym.name}"
        if rhs:
            return f"{sym.name}: TypeAlias = {rhs}"
        return f"{sym.name}: TypeAlias"

    if ai.source_str:
        return f"{sym.name} = {_unquoted_type_args(ai.source_str)}"
    return ""


def _unquoted_type_args(call: str) -> str:
    """*call* (``TypeVar('T', 'date', bound='Base')``) with its string type arguments unquoted.

    The name stays quoted; a stub needs no forward-reference quotes, and unquoted names get imported.

    Examples
    --------
    >>> _unquoted_type_args("TypeVar('T', int, 'date', bound='Base')")
    "TypeVar('T', int, date, bound=Base)"
    >>> _unquoted_type_args("NewType('UserId', int)")
    "NewType('UserId', int)"
    """
    try:
        node = ast.parse(call, mode="eval").body
    except SyntaxError:
        return call
    if not isinstance(node, ast.Call) or not node.args:
        return call
    changed = False

    def unquote(value: ast.expr) -> ast.expr:
        nonlocal changed
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            try:
                parsed = ast.parse(value.value, mode="eval").body
            except SyntaxError:
                return value
            changed = True
            return parsed
        return value

    node.args[1:] = [unquote(a) for a in node.args[1:]]
    for kw in node.keywords:
        if kw.arg in ("bound", "default"):
            kw.value = unquote(kw.value)
    return ast.unparse(node) if changed else call
