"""
``PyArg_Parse*`` and ``Py_BuildValue`` format strings, and Argument Clinic input blocks, as signatures.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from ..._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_POS
from .._constants import CAPI_CLINIC_TYPES, CAPI_FORMAT_ARGS, CAPI_FORMAT_TYPES, CAPI_TYPE_OBJECTS
from ..signatures import Param, Signature

_CLINIC = re.compile(r"/\*\[clinic input\]\s*\n(.*?)\[clinic start generated code\]", re.S)
_CLINIC_SKIP = ("module ", "class ", "output ", "preserve", "dump ", "destination ", "set ", "@")
_CLINIC_RECEIVERS = ("self", "defining_class")


@dataclass(frozen=True)
class Unit:
    """One top-level ``PyArg_Parse*`` format unit: its code, Python type, varargs consumed, ``|`` and ``$`` state."""
    code: str
    type: str | None
    args: int
    optional: bool
    kw_only: bool


def _unit_code(fmt: str, i: int) -> str:
    """The format unit starting at *i* (``i``, ``s#``, ``O!``, ``es#``)."""
    code = fmt[i]
    if code == "e" and i + 1 < len(fmt):
        code += fmt[i + 1]
        return code + "#" if fmt[i + 2:i + 3] == "#" else code
    if fmt[i + 1:i + 2] in ("#", "*", "!", "&") and code + fmt[i + 1] in CAPI_FORMAT_TYPES:
        return code + fmt[i + 1]
    return code


def parse_units(fmt: str) -> tuple[list[Unit], str | None] | None:
    """The top-level units of a ``PyArg_Parse*`` *fmt* and its ``:name``; ``None`` when a unit is unknown."""
    units, optional, kw_only, i = [], False, False, 0
    while i < len(fmt):
        ch = fmt[i]
        if ch in ":;":
            return units, fmt[i + 1:] or None if ch == ":" else None
        if ch == "|":
            optional, i = True, i + 1
            continue
        if ch == "$":
            kw_only, i = True, i + 1
            continue
        if ch == "(":
            end = _group_end(fmt, i)
            inner = parse_units(fmt[i + 1:end]) if end > 0 else None
            if inner is None:
                return None
            types = ", ".join(u.type or "Any" for u in inner[0])
            units.append(Unit("(", f"tuple[{types}]", sum(u.args for u in inner[0]), optional, kw_only))
            i = end + 1
            continue
        code = _unit_code(fmt, i)
        if code not in CAPI_FORMAT_TYPES:
            return None
        units.append(Unit(code, CAPI_FORMAT_TYPES[code], CAPI_FORMAT_ARGS.get(code, 1), optional, kw_only))
        i += len(code)
    return units, None


def _group_end(fmt: str, at: int) -> int:
    depth = 0
    for i in range(at, len(fmt)):
        depth += {"(": 1, ")": -1}.get(fmt[i], 0)
        if depth == 0:
            return i
    return -1


def format_signature(units: list[Unit], names: list[str], *, keywords: bool, varargs: list[str],
                     types: dict[str, str]) -> Signature:
    """The signature *units* parse; *names* come from ``kwlist`` (*keywords*) or the C variables."""
    params, used = [], 0
    for i, unit in enumerate(units):
        name = names[i] if i < len(names) and names[i] else f"arg{i}"
        annotation = unit.type
        if unit.code == "O!" and used < len(varargs):
            annotation = _type_object(varargs[used], types)
        kind = KW_ONLY if unit.kw_only else POS_KW if keywords and i < len(names) and names[i] else POS_ONLY
        params.append(Param(name, kind, annotation or "Any", "..." if unit.optional or unit.kw_only else None))
        used += unit.args
    return Signature(tuple(params))


def _type_object(arg: str, types: dict[str, str]) -> str | None:
    """The Python type an ``O!`` type argument (``&PyList_Type``, ``&MyType``) names, or ``None``."""
    name = arg.strip().lstrip("&").strip()
    name = re.sub(r"^\(\s*\w+\s*\*\s*\)\s*&?", "", name)
    return CAPI_TYPE_OBJECTS.get(name) or types.get(name)


def build_type(fmt: str) -> str | None:
    """The Python type ``Py_BuildValue(fmt, ...)`` returns, or ``None`` when *fmt* is not plain."""
    items = _build_items(fmt)
    if items is None:
        return None
    if not items:
        return "None"
    return items[0] if len(items) == 1 else f"tuple[{', '.join(items)}]"


def _build_items(fmt: str) -> list[str] | None:
    items, i = [], 0
    while i < len(fmt):
        ch = fmt[i]
        if ch in " \t,:":
            i += 1
        elif ch in "([{":
            close = {"(": ")", "[": "]", "{": "}"}[ch]
            end = fmt.find(close, i)
            inner = _build_items(fmt[i + 1:end]) if end > 0 and fmt.find(ch, i + 1, end) < 0 else None
            if inner is None:
                return None
            items.append(f"tuple[{', '.join(inner)}]" if ch == "(" else "list" if ch == "[" else "dict")
            i = end + 1
        else:
            code = _unit_code(fmt, i)
            if code not in CAPI_FORMAT_TYPES and code not in ("S", "N"):
                return None
            items.append(CAPI_FORMAT_TYPES.get(code) or "Any")
            i += len(code)
    return items


def clinic_blocks(text: str) -> list[tuple[str, Signature]]:
    """``(dotted name, signature)`` for every Argument Clinic function block in raw *text*."""
    found = []
    for m in _CLINIC.finditer(text):
        parsed = _clinic_function(m[1].splitlines())
        if parsed is not None:
            found.append(parsed)
    return found


def _clinic_function(lines: list[str]) -> tuple[str, Signature] | None:
    """One clinic block's function; ``None`` for directives, clones and optional groups."""
    body = [line.rstrip() for line in lines]
    head = next((i for i, line in enumerate(body) if line and not line.startswith(_CLINIC_SKIP)), None)
    if head is None or body[head][0].isspace() or "=" in body[head]:
        return None
    m = re.match(r"^([\w.]+)(?:\s+as\s+\w+)?\s*(?:->\s*(\w+))?\s*$", body[head])
    if m is None:
        return None
    params: list[Param] = []
    kind, indent = POS_KW, None
    for line in body[head + 1:]:
        if not line:
            continue
        width = len(line) - len(line.lstrip())
        if width == 0:
            break
        indent = indent if indent is not None else width
        if width > indent:
            continue
        item = line.strip()
        if item.startswith("/"):
            params = [Param(p.name, POS_ONLY, p.annotation, p.default) if p.kind is POS_KW else p for p in params]
        elif item == "*":
            kind = KW_ONLY
        elif item in ("[", "]"):
            return None
        else:
            param = _clinic_param(item, kind)
            if param is not None:
                params.append(param)
                kind = KW_ONLY if param.kind is VAR_POS else kind
    returns = CAPI_CLINIC_TYPES.get(m[2]) if m[2] and m[2] != "object" else None
    return m[1], Signature(tuple(params), returns)


def _clinic_param(item: str, kind: object) -> Param | None:
    m = re.match(r"^(\*?)(\w+)(?:\s+as\s+\w+)?\s*:\s*(\w+)\s*(\((.*)\))?\s*(?:=\s*(.*))?$", item)
    if m is None or m[3] in _CLINIC_RECEIVERS:
        return None
    annotation = _clinic_type(m[3], m[5] or "")
    default = _clinic_default(m[6])
    if default == "None" and annotation not in ("Any", "None") and "None" not in annotation.split(" | "):
        annotation += " | None"
    if m[1]:
        return Param(m[2], VAR_POS, "Any" if m[3] in ("object", "tuple", "array") else annotation)
    return Param(m[2], kind, annotation, default)


def _clinic_type(converter: str, options: str) -> str:
    accept = re.search(r"accept\s*=\s*\{([^}]*)\}", options)
    if accept:
        kinds = [CAPI_CLINIC_TYPES.get(k.strip()) or _buffer(k.strip()) for k in accept[1].split(",")]
        if all(kinds):
            return " | ".join(dict.fromkeys(kinds))
    sub = re.search(r"subclass_of\s*=\s*['\"]&?(\w+)['\"]", options)
    if sub:
        return CAPI_TYPE_OBJECTS.get(sub[1], "Any")
    return CAPI_CLINIC_TYPES.get(converter, "Any")


def _buffer(name: str) -> str | None:
    return "typing_extensions.Buffer" if name in ("buffer", "robuffer", "rwbuffer") else None


def _clinic_default(text: str | None) -> str | None:
    if text is None:
        return None
    text = text.strip()
    try:
        ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return "..."
    return text
