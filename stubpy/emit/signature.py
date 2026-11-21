"""
Signature assembly: ``/`` and ``*`` separators, parameter strings and ``def`` layout.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY, UNINFORMATIVE_DEFAULT_TYPES, VAR_POS
from stubpy.emit._constants import KW_SEP_NAME, POS_SEP_NAME
from stubpy.resolve import ParamWithHints

from .annotations.defaults import NonLiteralDefault


def insert_kw_separator(params_with_hints: list[ParamWithHints]) -> list[ParamWithHints]:
    """Insert a bare ``*`` sentinel before the first keyword-only parameter.

    Nothing is inserted when there is already a ``*args`` or no keyword-only parameter.

    Parameters
    ----------
    params_with_hints : list of tuple
        ``(inspect.Parameter, hints)`` pairs.

    Returns
    -------
    list of tuple
        The pairs, with the sentinel parameter named ``__kw_sep__`` added when needed.

    See Also
    --------
    insert_pos_separator : Adds the ``/`` sentinel.
    with_separators : Applies both.

    Examples
    --------
    >>> kw = inspect.Parameter("b", inspect.Parameter.KEYWORD_ONLY)
    >>> pos = inspect.Parameter("a", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    >>> insert_kw_separator([(pos, {}), (kw, {})])[1][0].name
    '__kw_sep__'
    """
    if any(p.kind == VAR_POS for p, _ in params_with_hints):
        return params_with_hints

    kw_indices = [i for i, (p, _) in enumerate(params_with_hints) if p.kind == KW_ONLY]
    if not kw_indices:
        return params_with_hints

    result = list(params_with_hints)
    result.insert(kw_indices[0], (inspect.Parameter(KW_SEP_NAME, VAR_POS), {}))
    return result


def insert_pos_separator(params_with_hints: list[ParamWithHints]) -> list[ParamWithHints]:
    """Insert a bare ``/`` sentinel after the last positional-only parameter (PEP 570).

    Parameters
    ----------
    params_with_hints : list of tuple
        ``(inspect.Parameter, hints)`` pairs.

    Returns
    -------
    list of tuple
        The pairs, with the sentinel parameter named ``__pos_sep__`` added when needed.

    See Also
    --------
    insert_kw_separator : Adds the ``*`` sentinel.
    with_separators : Applies both.

    Examples
    --------
    >>> a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
    >>> b = inspect.Parameter("b", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    >>> insert_pos_separator([(a, {}), (b, {})])[1][0].name
    '__pos_sep__'
    """
    last_pos_only = -1
    for i, (p, _) in enumerate(params_with_hints):
        if p.kind == POS_ONLY:
            last_pos_only = i

    if last_pos_only < 0:
        return params_with_hints

    result = list(params_with_hints)
    result.insert(last_pos_only + 1, (inspect.Parameter(POS_SEP_NAME, POS_KW), {}))
    return result


def with_separators(params_with_hints: list[ParamWithHints]) -> list[ParamWithHints]:
    """Apply :func:`insert_pos_separator` then :func:`insert_kw_separator`.

    Parameters
    ----------
    params_with_hints : list of tuple
        ``(inspect.Parameter, hints)`` pairs.

    Returns
    -------
    list of tuple
        The pairs with the ``/`` and ``*`` sentinels added where needed.

    Examples
    --------
    >>> a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
    >>> b = inspect.Parameter("b", inspect.Parameter.KEYWORD_ONLY)
    >>> [p.name for p, _ in with_separators([(a, {}), (b, {})])]
    ['a', '__pos_sep__', '__kw_sep__', 'b']
    """
    return insert_kw_separator(insert_pos_separator(params_with_hints))


def unique(items: list) -> list:
    """Return *items* without repeats, keeping the first of each.

    Parameters
    ----------
    items : list
        The items; they need only support ``==``.

    Returns
    -------
    list
        The items in first-seen order.

    Examples
    --------
    >>> unique([1, 2, 1, 3, 2])
    [1, 2, 3]
    """
    out: list = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def structural_return(info: Any) -> str:
    """Return the type a function's shape implies, or ``""``.

    Covers literal generators and functions that always raise.

    Parameters
    ----------
    info : object
        The function's AST info, or any object; ``None`` is accepted.

    Returns
    -------
    str
        The ``structural_return`` attribute of *info*, or ``""``.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> structural_return(SimpleNamespace(structural_return="Iterator[int]"))
    'Iterator[int]'
    >>> structural_return(None)
    ''
    """
    return getattr(info, "structural_return", None) or ""


def generic_name(name: str, info: object) -> str:
    """Return *name* with its PEP 695 type parameters when the source declares any.

    Parameters
    ----------
    name : str
        The function or class name.
    info : object
        The AST info, whose ``type_params`` list is read.

    Returns
    -------
    str
        ``first[T]``-style text, or *name* unchanged.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> generic_name("first", SimpleNamespace(type_params=["T"]))
    'first[T]'
    >>> generic_name("first", None)
    'first'
    """
    params = getattr(info, "type_params", None)
    return f"{name}[{', '.join(params)}]" if params else name


def receiver_text(name: str, annotation: str) -> str:
    """Return the receiver parameter: ``self``, or ``self: E`` when the source annotates it.

    Parameters
    ----------
    name : str
        The receiver name, ``"self"`` or ``"cls"``.
    annotation : str
        The source annotation, or ``""``.

    Returns
    -------
    str
        The receiver as written in the signature.

    Examples
    --------
    >>> receiver_text("self", "")
    'self'
    >>> receiver_text("self", "E")
    'self: E'
    """
    return f"{name}: {annotation}" if annotation else name


def infer_default_type(p: inspect.Parameter, covered: dict[str, str]) -> str | None:
    """Infer a type from a parameter's runtime default.

    Nothing is inferred when the parameter has no default, is already typed
    by *covered*, or the default is ``None``, ``...``, a non-literal
    expression, a class, an instance of a non-builtin type (``numpy.float64``
    could not be named without an import) or of an uninformative type.

    Parameters
    ----------
    p : inspect.Parameter
        The parameter.
    covered : dict of str to str
        Parameter names that already have a type from another source.

    Returns
    -------
    str or None
        The type name of the default, or ``None``.

    Examples
    --------
    >>> p = inspect.Parameter("n", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=3)
    >>> infer_default_type(p, {})
    'int'
    >>> infer_default_type(p, {"n": "float"}) is None
    True
    """
    if p.default is inspect.Parameter.empty:
        return None
    if covered and p.name in covered:
        return None
    d = p.default
    if isinstance(d, NonLiteralDefault) or d is None or d is ...:
        return None
    if isinstance(d, type) or type(d).__module__ != "builtins":
        return None
    t = type(d).__name__
    return t if t not in UNINFORMATIVE_DEFAULT_TYPES and not t.startswith("_") else None


def render_params(
    params_with_hints: list[ParamWithHints],
    format_one: Callable[[inspect.Parameter, dict[str, Any]], str],
) -> list[str]:
    """Render each parameter with *format_one*, turning separator sentinels into ``*`` and ``/``.

    Parameters
    ----------
    params_with_hints : list of tuple
        ``(inspect.Parameter, hints)`` pairs, usually from :func:`with_separators`.
    format_one : callable
        Renders one ``(parameter, hints)`` pair as text.

    Returns
    -------
    list of str
        One string per parameter or separator.

    Examples
    --------
    >>> a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
    >>> b = inspect.Parameter("b", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    >>> render_params(with_separators([(a, {}), (b, {})]), lambda p, h: p.name)
    ['a', '/', 'b']
    """
    return [
        "*" if p.name == KW_SEP_NAME
        else "/" if p.name == POS_SEP_NAME
        else format_one(p, h)
        for p, h in params_with_hints
    ]
