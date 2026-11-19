"""
Bracket-aware splitting and type / default normalization of signature text.
"""
from __future__ import annotations

import ast
import re

__all__ = ["C_TYPES", "normalize_type", "default_text", "split_top", "matching_paren", "c_return_type"]

C_TYPES: dict[str, str] = {
    "double": "float",
    "float": "float",
    "long double": "float",
    "int": "int",
    "long": "int",
    "long long": "int",
    "short": "int",
    "char": "int",
    "unsigned": "int",
    "unsigned int": "int",
    "unsigned long": "int",
    "unsigned long long": "int",
    "size_t": "int",
    "Py_ssize_t": "int",
    "bint": "bool",
    "bool": "bool",
    "object": "Any",
    "str": "str",
    "unicode": "str",
    "bytes": "bytes",
    "list": "list",
    "dict": "dict",
    "tuple": "tuple",
    "set": "set",
    "void": "None",
}

BUFFER_TYPE = "typing_extensions.Buffer"
ANY_ARRAY = "numpy.typing.NDArray[typing.Any]"

_TYPING_TO_BUILTIN = {
    "List": "list", "Dict": "dict", "Tuple": "tuple", "Set": "set",
    "FrozenSet": "frozenset", "Type": "type",
}
_MEMORYVIEW = re.compile(r"^[A-Za-z_][\w ]*\[[\s:,\d]*:[\s:,\d]*\]$")
_NB_NDARRAY = re.compile(r"\b(?:numpy\.)?ndarray\[([^\[\]]*=[^\[\]]*)\]")
_NB_DTYPE = re.compile(r"\bdtype\s*=\s*([A-Za-z_]\w*)")
_BARE_NDARRAY = re.compile(r"(?<![\w.])ndarray\b")
_ENUM_REPR = re.compile(r"<([A-Za-z_]\w*\.[A-Za-z_]\w*): [^<>]*>")
_TYPING_PREFIX = re.compile(r"\b(?:typing\.)?(" + "|".join(_TYPING_TO_BUILTIN) + r")\b")


def split_top(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside brackets and quotes."""
    out, depth, quote, start = [], 0, "", 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in "([{<":
            depth += 1
        elif ch in ")]}>" and depth:
            depth -= 1
        elif ch == sep and depth == 0:
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return [s.strip() for s in out if s.strip()]


def matching_paren(text: str, open_at: int) -> int:
    """Index of the parenthesis closing the one at ``open_at``, or -1."""
    depth, quote = 0, ""
    for i in range(open_at, len(text)):
        ch = text[i]
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def normalize_type(text: str | None, c_style: bool = False) -> str | None:
    """A valid annotation from binding type text, or ``None``."""
    if not text:
        return None
    text = " ".join(text.split())
    if c_style:
        if _MEMORYVIEW.match(text):
            return BUFFER_TYPE
        text = C_TYPES.get(text, text.replace(" ", "_") if " " in text else text)
    text = _NB_NDARRAY.sub(_nanobind_array, text)
    text = _BARE_NDARRAY.sub("numpy.ndarray", text)
    text = _TYPING_PREFIX.sub(lambda m: _TYPING_TO_BUILTIN[m.group(1)], text)
    try:
        ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    return text


def _nanobind_array(m: re.Match[str]) -> str:
    """``numpy.typing.NDArray[numpy.<dtype>]`` for nanobind's ``ndarray[dtype=..., shape=...]``."""
    dtype = _NB_DTYPE.search(m.group(1))
    return f"numpy.typing.NDArray[numpy.{dtype.group(1)}]" if dtype else ANY_ARRAY


def c_return_type(text: str | None) -> str | None:
    """A return annotation, mapping a bare C type (``void``, ``double``) to its Python type."""
    if text and " ".join(text.split()) in C_TYPES:
        return normalize_type(text, c_style=True)
    return normalize_type(text)


def default_text(text: str) -> str:
    """Default source when it is a safe literal or dotted name, ``Cls.MEMBER`` for an enum repr, else ``...``."""
    text = text.strip()
    member = _ENUM_REPR.fullmatch(text)
    if member:
        return member.group(1)
    if not text or text == "*" or text.startswith("<"):
        return "..."
    try:
        ast.literal_eval(text)
        return text
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        pass
    if re.fullmatch(r"[A-Za-z_][\w.]*", text) and text not in ("inf", "nan"):
        return text if "." in text or text in ("None", "True", "False") else "..."
    return "..."
