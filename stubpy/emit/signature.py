"""
Signature assembly: ``/`` and ``*`` separators, parameter strings and ``def`` layout.
"""
from __future__ import annotations

import ast
import inspect
import io
import tokenize
from collections.abc import Callable
from typing import Any

from stubpy._constants import (
    KW_ONLY,
    KW_SEP_NAME,
    POS_KW,
    POS_ONLY,
    POS_SEP_NAME,
    UNINFORMATIVE_DEFAULT_TYPES,
    VAR_KW,
    VAR_POS,
)
from stubpy.compiled.runtime import overload_count
from stubpy.core.diagnostics import Stage
from stubpy.resolve import ParamWithHints, local_target

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
    expression or of an uninformative type.

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
    t = type(d).__name__
    return t if t not in UNINFORMATIVE_DEFAULT_TYPES and not t.startswith("_") else None


def warn_dynamic_kwargs(
    name: str, params_with_hints: list[ParamWithHints], ast_info: Any, ctx: Any,
) -> None:
    """Report a ``**kwargs`` that stays in the stub although the function forwards it.

    A callee that cannot be named statically gives a WARNING. Named
    callees that left ``**kwargs`` open (unresolvable, or accepting
    arbitrary keywords themselves) give an INFO, a WARNING under ``verbose``.

    Parameters
    ----------
    name : str
        The qualified function name, used as the diagnostic symbol.
    params_with_hints : list of tuple
        The final ``(inspect.Parameter, hints)`` pairs; nothing is reported without a ``**kwargs``.
    ast_info : object
        The function's AST info, which records where ``**kwargs`` is forwarded.
    ctx : StubContext
        The run context that collects the diagnostics.

    Returns
    -------
    None

    See Also
    --------
    note_compiled_overloads : The equivalent report for overloaded compiled callees.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> from stubpy.core.context import StubContext
    >>> ctx = StubContext()
    >>> kw = inspect.Parameter("kw", inspect.Parameter.VAR_KEYWORD)
    >>> warn_dynamic_kwargs("f", [(kw, {})], SimpleNamespace(kwargs_dynamic=True), ctx)
    >>> len(ctx.diagnostics.warnings)
    1
    """
    if not any(p.kind == VAR_KW for p, _ in params_with_hints):
        return
    if getattr(ast_info, "kwargs_dynamic", False):
        ctx.diagnostics.warning(
            Stage.RESOLVE, name,
            "**kwargs is passed to a callee that cannot be resolved statically; kept as **kwargs",
        )
        return
    targets = list(getattr(ast_info, "kwargs_forwarded_to", []) or []) + list(
        getattr(ast_info, "kwargs_method_targets", []) or []
    )
    if targets:
        report = ctx.diagnostics.warning if getattr(ctx.config, "verbose", False) else ctx.diagnostics.info
        report(
            Stage.RESOLVE, name,
            f"**kwargs forwarded to {', '.join(targets)} is kept: the callee could not be resolved "
            "or accepts arbitrary keywords itself",
        )


def _first_definition(cls: type, method_name: str) -> Any:
    """The *method_name* of the first class after *cls* in its MRO that defines it."""
    for parent in cls.__mro__[1:]:
        if method_name in vars(parent):
            return vars(parent)[method_name]
    return None


def forwarding_callees(ast_info: Any, namespace: dict[str, Any], cls: type | None = None,
                       method_name: str = "") -> list[tuple[str, Any]]:
    """Return ``(label, callable)`` for each callee a function or method forwards its variadics to.

    A forward to the method's own name resolves to the first definition
    further up the MRO of *cls* (labelled ``super().name``); a forwarded class resolves to its
    ``__init__``.

    Parameters
    ----------
    ast_info : object
        The AST info, which names the forwarded-to callees.
    namespace : dict of str to Any
        The module namespace the names resolve in.
    cls : type, optional
        The class owning the method. Defaults to None.
    method_name : str, optional
        The method's name. Defaults to ``""``.

    Returns
    -------
    list of tuple of (str, Any)
        The resolved callees; names that do not resolve are left out.

    Examples
    --------
    >>> from types import SimpleNamespace
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> info = ast_harvest("def f(**kw):\\n    print(**kw)").functions[0]
    >>> forwarding_callees(info, {"print": print})
    [('print', <built-in function print>)]
    """
    names = list(getattr(ast_info, "kwargs_forwarded_to", []) or []) + list(
        getattr(ast_info, "args_forwarded_to", []) or [])
    found: list[tuple[str, Any]] = []
    for name in dict.fromkeys(names):
        if cls is not None and name == method_name:
            target = _first_definition(cls, method_name)
            if target is not None:
                found.append((f"super().{method_name}", target))
            continue
        target = local_target(ast_info, name, namespace) or namespace.get(name)
        if isinstance(target, type):
            init = vars(target).get("__init__") or _first_definition(target, "__init__")
            found.append((f"{name}.__init__", init))
        elif target is not None:
            found.append((name, target))
    return found


def note_compiled_overloads(name: str, params_with_hints: list[ParamWithHints],
                            callees: list[tuple[str, Any]], ctx: Any) -> None:
    """Record an INFO when variadics stay open because a callee is an overloaded compiled callable.

    Parameters
    ----------
    name : str
        The qualified function name, used as the diagnostic symbol.
    params_with_hints : list of tuple
        The final ``(inspect.Parameter, hints)`` pairs; nothing is recorded without ``*args`` or ``**kwargs``.
    callees : list of tuple of (str, Any)
        ``(label, callable)`` pairs from :func:`forwarding_callees`.
    ctx : StubContext
        The run context that collects the diagnostics.

    Returns
    -------
    None

    See Also
    --------
    warn_dynamic_kwargs : The report for unresolved ``**kwargs``.
    forwarding_callees : Finds the callees.
    """
    if not any(p.kind in (VAR_KW, VAR_POS) for p, _ in params_with_hints):
        return
    for label, target in callees:
        count = overload_count(target)
        if count > 1:
            ctx.diagnostics.info(
                Stage.RESOLVE, name,
                f"{label} is compiled with {count} overloads; *args / **kwargs are kept "
                "(overloads are not expanded into the caller)",
            )


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


def comment_start(text: str) -> int | None:
    """Return the offset of a trailing ``#`` comment in one parameter's text.

    A ``#`` inside a string literal is ignored.

    Parameters
    ----------
    text : str
        One parameter's source text.

    Returns
    -------
    int or None
        The column of the comment, or ``None`` when there is none.

    Examples
    --------
    >>> comment_start("x: int = 1  # count")
    12
    >>> comment_start("sep: str = '#'") is None
    True
    """
    if "#" not in text:
        return None
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                return tok.start[1]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return None
    return None


def join_params_multiline(param_strs: list[str], inner: str) -> str:
    """Join parameters one per line, putting each trailing comma before any ``#`` comment.

    Parameters
    ----------
    param_strs : list of str
        The rendered parameters.
    inner : str
        The indentation of each parameter line.

    Returns
    -------
    str
        The parameter lines joined by newlines, without the first line's indentation.

    See Also
    --------
    format_def : Uses this for long signatures.

    Examples
    --------
    >>> print(join_params_multiline(["a: int  # first", "b"], "    "))
    a: int,  # first
        b,
    """
    parts: list[str] = []
    for s in param_strs:
        idx = comment_start(s)
        if idx is not None:
            parts.append(f"{s[:idx].rstrip()},  {s[idx:]}")
        else:
            parts.append(s + ",")
    return (f"\n{inner}").join(parts)


def format_def(
    indent: str,
    keyword: str,
    name: str,
    param_strs: list[str],
    ret_part: str,
    n_params: int,
    body: str = "...",
) -> list[str]:
    """Lay out a ``def``: inline for up to two parameters, otherwise one per line.

    A parameter with a trailing comment also forces the multi-line layout.

    Parameters
    ----------
    indent : str
        The indentation of the ``def`` line.
    keyword : str
        ``"def"`` or ``"async def"``.
    name : str
        The function name.
    param_strs : list of str
        The rendered parameters, receiver included.
    ret_part : str
        The return clause such as ``" -> int"``, or ``""``.
    n_params : int
        The parameter count that decides the layout, usually without the receiver.
    body : str, optional
        The body text. Defaults to ``"..."``.

    Returns
    -------
    list of str
        The stub lines.

    See Also
    --------
    hinted_def : Lays out a ``def`` from hinted signature text.

    Examples
    --------
    >>> format_def("", "def", "f", ["a: int", "b: int"], " -> int", 2)
    ['def f(a: int, b: int) -> int: ...']
    """
    if n_params <= 2 and not any(comment_start(s) is not None for s in param_strs):
        sig = f"{indent}{keyword} {name}({', '.join(param_strs)}){ret_part}"
        if body == "...":
            return [f"{sig}: ..."]
        return [f"{sig}:", f"{indent}    {body}"]

    inner = indent + "    "
    lines = [f"{indent}{keyword} {name}(", f"{inner}{join_params_multiline(param_strs, inner)}"]
    if body == "...":
        lines.append(f"{indent}){ret_part}: ...")
    else:
        lines.append(f"{indent}){ret_part}:")
        lines.append(f"{indent}    {body}")
    return lines


def hinted_def(indent: str, keyword: str, name: str, text: str, ctx: Any, body: str = "...") -> list[str] | None:
    """Lay out a ``def`` from ``@hint.signature`` text.

    Parameters
    ----------
    indent : str
        The indentation of the ``def`` line.
    keyword : str
        ``"def"`` or ``"async def"``.
    name : str
        The function name.
    text : str
        The signature text starting at the opening parenthesis, return clause included.
    ctx : StubContext
        The run context that collects the warning.
    body : str, optional
        The body text. Defaults to ``"..."``.

    Returns
    -------
    list of str or None
        The stub lines, or ``None``, with a WARNING, when the text does not parse.

    See Also
    --------
    format_def : Lays out a ``def`` from rendered parameters.

    Examples
    --------
    >>> from stubpy.core.context import StubContext
    >>> hinted_def("", "def", "f", "(x: int) -> str", StubContext())
    ['def f(x: int) -> str: ...']
    """
    try:
        ast.parse(f"def _{text}: ...")
    except SyntaxError as exc:
        ctx.diagnostics.warning(Stage.EMIT, name, f"Ignoring @hint.signature({text!r}): {exc.msg}")
        return None
    line = f"{indent}{keyword} {name}{text}"
    return [f"{line}: ..."] if body == "..." else [f"{line}:", f"{indent}    {body}"]
