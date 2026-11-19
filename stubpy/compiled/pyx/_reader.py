"""A dependency-free reader of the Python-visible declarations of a ``.pyx`` file."""
from __future__ import annotations

import ast
import re

from ..signatures import matching_paren, split_top
from .models import PyxClass, PyxEnum, PyxFunction, PyxModule, PyxParam

_HEAD = re.compile(r"^(?:async\s+)?(def|cpdef)\s+(.*)$", re.S)
_CLASS = re.compile(r"^(?:cdef\s+(?:public\s+|api\s+)*)?class\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?\s*:")
_ENUM = re.compile(r"^cpdef\s+enum\s+(?:class\s+)?([A-Za-z_]\w*)\s*:")
_FIELD = re.compile(r"^cdef\s+(public|readonly)\s+(.+?)\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*$")
_MODIFIERS = {"inline", "api", "public", "static"}
_TAIL = re.compile(r"\b(nogil|noexcept|with\s+gil|except\s*[+*?]?\s*[^:]*?)\s*$")
_STRING = re.compile(r"^[rRuUbB]{0,2}('''|\"\"\"|'|\")")


def _statements(text: str) -> list[tuple[int, str]]:
    """``(indent, logical line)`` pairs: comments dropped, bracketed continuations and triple strings joined."""
    out: list[tuple[int, str]] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    indent = 0
    for raw in text.splitlines():
        if not buf:
            if not raw.strip():
                continue
            indent = len(raw) - len(raw.lstrip())
        line, depth, quote = _scan(raw, depth, quote)
        buf.append(line)
        if depth > 0 or quote is not None or line.rstrip().endswith("\\"):
            continue
        joined = "\n".join(buf).strip() if any('"""' in b or "'''" in b for b in buf) else " ".join(
            b.strip().rstrip("\\") for b in buf)
        if joined:
            out.append((indent, joined))
        buf = []
    return out


def _scan(line: str, depth: int, quote: str | None) -> tuple[str, int, str | None]:
    """Track bracket depth and open strings through *line*; return it without a trailing comment."""
    i = 0
    while i < len(line):
        if quote is not None:
            if line.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 2 if line[i] == "\\" else 1
            continue
        ch = line[i]
        if ch == "#":
            return line[:i], depth, None
        if line.startswith(('"""', "'''"), i):
            quote = line[i:i + 3]
            i += 3
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(depth - 1, 0)
        i += 1
    if quote in ("'", '"'):
        quote = None
    return line, depth, quote


def _docstring(stmts: list[tuple[int, str]], i: int, indent: int) -> str | None:
    """The docstring opening the block that starts after statement *i*."""
    if i + 1 < len(stmts) and stmts[i + 1][0] > indent and _STRING.match(stmts[i + 1][1]):
        try:
            value = ast.literal_eval(stmts[i + 1][1])
        except (ValueError, SyntaxError):
            return None
        return value if isinstance(value, str) else None
    return None


def _param(text: str) -> PyxParam | None:
    text = re.sub(r"\s+(?:not|or)\s+None\b", "", text.strip())
    star = text[: len(text) - len(text.lstrip("*"))]
    text = text[len(star):].strip()
    default = None
    head, eq, tail = text.partition("=")
    if eq and "[" not in tail[:1]:
        text, default = head.strip(), tail.strip()
    if ":" in text and "[" not in text:
        name, _, ann = text.partition(":")
        return PyxParam(name.strip(), ann.strip() or None, default, star)
    found = re.search(r"([A-Za-z_]\w*)\s*$", text)
    if not found:
        return None
    ctype = text[: found.start()].strip() or None
    return PyxParam(found.group(1), ctype, default, star)


def _function(header: str, decorators: list[str], doc: str | None) -> PyxFunction | None:
    """Parse ``def name(args) -> R:`` or ``cpdef [mods] [ret] name(args) [except ...] [nogil]:``."""
    m = _HEAD.match(header)
    if not m:
        return None
    kind, rest = m.groups()
    open_at = rest.find("(")
    close_at = matching_paren(rest, open_at) if open_at >= 0 else -1
    if close_at < 0:
        return None
    before = rest[:open_at].split()
    if not before:
        return None
    name = before[-1]
    ret_words = [w for w in before[:-1] if w not in _MODIFIERS]
    after = rest[close_at + 1:].rstrip().rstrip(":").strip()
    after = _TAIL.sub("", after).strip()
    returns = after[2:].strip() if after.startswith("->") else (" ".join(ret_words) if kind == "cpdef" else None)
    fn = PyxFunction(name, returns=returns or None, doc=doc, decorators=decorators)
    for raw in split_top(rest[open_at + 1:close_at]):
        if raw.strip() == "*":
            fn.kw_only = len(fn.params)
            continue
        if raw.strip() in ("", "/"):
            continue
        param = _param(raw)
        if param is not None:
            fn.params.append(param)
    return fn


def read_pyx(text: str) -> PyxModule:
    """Read the declarations of the Cython source *text* without Cython."""
    stmts = _statements(text)
    module = PyxModule(doc=_docstring([(-1, "")] + stmts, 0, -1))
    stack: list[tuple[int, PyxClass]] = []
    enum: tuple[int, PyxEnum] | None = None
    decorators: list[str] = []
    body_of: int | None = None
    for i, (indent, line) in enumerate(stmts):
        if body_of is not None and indent > body_of:
            continue
        body_of = None
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if enum is not None and indent <= enum[0]:
            enum = None
        if enum is not None:
            for part in line.split(","):
                name, _, value = part.partition("=")
                if name.strip().isidentifier():
                    enum[1].members.append((name.strip(), int(value) if value.strip().lstrip("-").isdigit() else None))
            continue
        if line.startswith("@"):
            decorators.append(line[1:].strip())
            continue
        owner = stack[-1][1] if stack else None
        if (found := _ENUM.match(line)) and owner is None:
            enum = (indent, PyxEnum(found.group(1)))
            module.enums.append(enum[1])
        elif found := _CLASS.match(line):
            bases = [b.strip() for b in (found.group(2) or "").split(",") if b.strip()]
            cls = PyxClass(found.group(1), bases, _docstring(stmts, i, indent))
            if owner is None:
                module.classes.append(cls)
            stack.append((indent, cls))
        elif owner is not None and (found := _FIELD.match(line)):
            for name in found.group(3).split(","):
                owner.attributes[name.strip()] = (found.group(2).strip(), found.group(1) == "readonly")
        elif fn := _function(line, decorators, _docstring(stmts, i, indent)):
            (owner.methods if owner is not None else module.functions).append(fn)
            body_of = indent
        elif line.startswith("cdef ") and line.endswith(":"):
            body_of = indent
        decorators = [] if not line.startswith("@") else decorators
    return module
