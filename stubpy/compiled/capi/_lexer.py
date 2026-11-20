"""
Just enough C lexing to find initialisers, function bodies and call arguments: no preprocessor, no parser.
"""
from __future__ import annotations

import re

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = frozenset(")]}")
_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
_FUNCTION = re.compile(r"^[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)\s*\(((?:[^;{}()]|\([^;{}()]*\))*)\)\s*\{", re.M)
_DIRECTIVE = re.compile(r"^[ \t]*#(?:[^\n]*\\\n)*[^\n]*", re.M)
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "0": "\0"}


def strip_comments(text: str) -> str:
    """*text* with ``/* */`` and ``//`` comments blanked, string and char literals kept."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(" " + "\n" * text.count("\n", i, j))
            i = j
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def strip_directives(text: str) -> str:
    """*text* with preprocessor lines (and their ``\\`` continuations) removed."""
    return _DIRECTIVE.sub("", text)


def closing(text: str, at: int) -> int:
    """Index of the bracket closing the one at *at*, or -1."""
    stack, i, n = [], at, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if ch in _OPEN:
            stack.append(_OPEN[ch])
        elif ch in _CLOSE:
            if not stack or stack.pop() != ch:
                return -1
            if not stack:
                return i
        i += 1
    return -1


def split_args(text: str) -> list[str]:
    """Split on top-level commas, outside brackets and literals."""
    out, depth, start, i, n = [], 0, 0, 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(text[start:i].strip())
            start = i + 1
        i += 1
    tail = text[start:].strip()
    return [*out, tail] if tail or out else out


def string_value(expr: str) -> str | None:
    """The value of *expr* when it is only (adjacent) string literals, else ``None``."""
    parts = list(_LITERAL.finditer(expr))
    if not parts or _LITERAL.sub("", expr).strip():
        return None
    return "".join(re.sub(r"\\(.)", lambda m: _ESCAPES.get(m[1], m[1]), p[1]) for p in parts)


def identifier(expr: str) -> str | None:
    """The name *expr* refers to once casts and ``&`` are dropped, or ``None``."""
    text = expr.strip()
    while True:
        cast = re.match(r"^\((?:[^()]|\([^()]*\))*\)\s*(?=[&\w(])", text)
        if not cast or text.startswith("(&") or re.fullmatch(r"\(\s*\w+\s*\)", text):
            break
        text = text[cast.end():]
    text = text.lstrip("&").strip()
    while text.startswith("(") and closing(text, 0) == len(text) - 1:
        text = text[1:-1].strip().lstrip("&").strip()
    return text if re.fullmatch(r"[A-Za-z_]\w*", text) else None


def initialisers(text: str, kinds: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """``(kind, name, body)`` for each ``kind name[] = { body };`` declaration of one of *kinds*."""
    pattern = re.compile(r"\b(?:struct\s+)?(" + "|".join(kinds) + r")\s+([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*=\s*\{")
    found = []
    for m in pattern.finditer(text):
        end = closing(text, m.end() - 1)
        if end > 0:
            found.append((m[1], m[2], text[m.end():end]))
    return found


def entries(body: str) -> list[list[str]]:
    """The ``{...}`` rows of an array initialiser *body*, each split into its fields."""
    rows, i = [], 0
    while True:
        i = body.find("{", i)
        if i < 0:
            return rows
        end = closing(body, i)
        if end < 0:
            return rows
        rows.append(split_args(body[i + 1:end]))
        i = end + 1


def fields(body: str) -> tuple[dict[str, str], list[str]]:
    """Designated ``.field = value`` initialisers of a struct *body*, and its positional values."""
    named, positional = {}, []
    body = re.sub(r"^\s*\w+_HEAD_INIT\b(?:\s*\([^()]*\))?\s*,?", "", body)
    for part in split_args(body):
        m = re.match(r"^\.(\w+)\s*=\s*(.*)$", part, re.S)
        if m:
            named[m[1]] = m[2].strip()
        else:
            positional.append(part)
    return named, positional


def functions(text: str) -> dict[str, tuple[list[str], str]]:
    """``{name: (parameter names, body)}`` for each top-level function definition."""
    found: dict[str, tuple[list[str], str]] = {}
    for m in _FUNCTION.finditer(text):
        if m[1] in ("if", "for", "while", "switch", "return", "sizeof"):
            continue
        end = closing(text, m.end() - 1)
        if end > 0:
            names = [re.findall(r"([A-Za-z_]\w*)\s*(?:\[\s*\])?\s*$", p) for p in split_args(m[2])]
            found.setdefault(m[1], ([n[0] if n else "" for n in names], text[m.end():end]))
    return found


def calls(body: str, name: str) -> list[list[str]]:
    """The argument lists of every call to the function *name* in *body*."""
    found = []
    for m in re.finditer(r"\b" + re.escape(name) + r"\s*\(", body):
        end = closing(body, m.end() - 1)
        if end > 0:
            found.append(split_args(body[m.end():end]))
    return found
