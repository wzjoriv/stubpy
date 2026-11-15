"""Parse ``name(params) -> ret`` lines and the signature lines at the top of docstrings."""
from __future__ import annotations

import re

from ..._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS
from ._text import c_return_type, default_text, matching_paren, normalize_type, split_top
from .models import Param, Signature

__all__ = ["parse_signature", "docstring_signatures", "strip_signature_lines"]

_PSEUDO_PARAMS = frozenset({"$self", "$module", "$type", "$cls"})
_OVERLOAD_LINE = re.compile(r"^\s*\d+\.\s+(.*)$")


def _parse_param(raw: str) -> Param | str | None:
    """A ``Param``, a ``/`` or ``*`` marker, or ``None`` for pseudo-parameters."""
    raw = raw.strip()
    if raw in ("/", "*"):
        return raw
    if raw in _PSEUDO_PARAMS or raw.split(":")[0].strip() in _PSEUDO_PARAMS:
        return None
    default = None
    parts = split_top(raw, "=")
    if len(parts) > 1:
        raw, default = parts[0], default_text("=".join(parts[1:]))
    kind = POS_KW
    if raw.startswith("**"):
        kind, raw = VAR_KW, raw[2:]
    elif raw.startswith("*"):
        kind, raw = VAR_POS, raw[1:]
    annotation = None
    if ":" in raw and raw.partition(":")[0].strip().isidentifier():
        name, _, ann = raw.partition(":")
        annotation = normalize_type(ann)
    else:
        tokens = raw.split()
        if len(tokens) > 1:
            name = tokens[-1].lstrip("*")
            annotation = normalize_type(" ".join(tokens[:-1]), c_style=True)
        else:
            name = raw
    name = name.strip()
    if not name.isidentifier():
        return None
    return Param(name, kind, annotation, default)


def parse_signature(text: str) -> tuple[str, Signature] | None:
    """Parse ``name(params) -> ret`` (``def`` prefix allowed) into ``(name, Signature)``."""
    text = text.strip()
    if text.startswith("def "):
        text = text[4:]
    open_at = text.find("(")
    if open_at <= 0:
        return None
    name = text[:open_at].strip().split(".")[-1]
    if not name.isidentifier():
        return None
    close_at = matching_paren(text, open_at)
    if close_at < 0:
        return None
    rest = text[close_at + 1:].strip().rstrip(":").strip()
    returns = c_return_type(rest[2:]) if rest.startswith("->") else None
    params: list[Param] = []
    kw_only = False
    seen_any = False
    for raw in split_top(text[open_at + 1:close_at]):
        item = _parse_param(raw)
        if item is None:
            continue
        if item == "/":
            params = [Param(p.name, POS_ONLY, p.annotation, p.default) for p in params]
            continue
        if item == "*":
            kw_only = True
            continue
        assert isinstance(item, Param)
        if item.kind == VAR_POS:
            kw_only = True
        elif kw_only and item.kind == POS_KW:
            item = Param(item.name, KW_ONLY, item.annotation, item.default)
        params.append(item)
        seen_any = True
    if not seen_any and text[open_at + 1:close_at].strip() not in ("", "/", "*"):
        return None
    return name, Signature(tuple(params), returns)


def _starts(line: str, name: str) -> bool:
    """True when ``line`` starts a signature of ``name``, plain or owner-qualified (``Cls.name(``)."""
    return re.match(rf"(?:[A-Za-z_][\w.]*\.)?{re.escape(name)}\(", line) is not None


def docstring_signatures(name: str, doc: str | None) -> list[Signature]:
    """Signatures written at the top of ``doc`` for ``name`` (pybind11, nanobind, Cython, C API styles)."""
    if not doc:
        return []
    lines = doc.strip().splitlines()
    found: list[Signature] = []
    if any(line.strip() == "Overloaded function." for line in lines[:3]):
        for line in lines:
            m = _OVERLOAD_LINE.match(line)
            if m and _starts(m.group(1).lstrip(), name):
                parsed = parse_signature(m.group(1))
                if parsed:
                    found.append(parsed[1])
        return found
    for line in lines:
        stripped = line.strip()
        if not _starts(stripped, name):
            break
        parsed = parse_signature(stripped)
        if not parsed:
            break
        found.append(parsed[1])
    return found


def strip_signature_lines(name: str, doc: str | None) -> str:
    """``doc`` without the leading signature lines and the pybind11 overload listing."""
    if not doc:
        return ""
    lines = doc.strip().splitlines()
    if any(line.strip() == "Overloaded function." for line in lines[:3]):
        body = [ln for ln in lines if not _OVERLOAD_LINE.match(ln)
                and ln.strip() not in ("Overloaded function.",) and not _starts(ln.strip(), name)]
        return re.sub(r"\n\s*\n(\s*\n)+", "\n\n", "\n".join(body)).strip()
    i = 0
    while i < len(lines) and _starts(lines[i].strip(), name) and parse_signature(lines[i]):
        i += 1
    if i < len(lines) and lines[i].strip() == "--":
        i += 1
    return "\n".join(lines[i:]).strip()
