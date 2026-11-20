"""
Layout of a ``def`` line: one line when it fits, one parameter per line otherwise, comments kept.
"""
from __future__ import annotations

import ast
import io
import tokenize
from typing import Any

from stubpy.state.diagnostics import Stage


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
    >>> from stubpy.state.context import StubContext
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
