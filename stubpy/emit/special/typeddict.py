"""TypedDict stubs."""
from __future__ import annotations

import re
import typing
from typing import Any

from stubpy.core.context import StubContext
from stubpy.emit.annotations import annotation_to_str
from stubpy.resolve import get_own_annotations

_QUALIFIERS = ("Required", "NotRequired", "ReadOnly")
_TEXT_RE = re.compile(r"^\s*(?:typing(?:_extensions)?\.)?(Required|NotRequired|ReadOnly)\s*\[(.*)\]\s*$", re.S)


def _qualifier_name(hint: Any) -> str | None:
    origin = typing.get_origin(hint)
    name = getattr(origin, "_name", None) or getattr(origin, "__name__", None)
    return name if name in _QUALIFIERS else None


def _raw_qualifiers(raw: Any) -> set[str]:
    """Return the field qualifiers written in a raw annotation, as an object or as source text."""
    found: set[str] = set()
    if isinstance(raw, typing.ForwardRef):
        raw = raw.__forward_arg__
    while True:
        if isinstance(raw, str):
            match = _TEXT_RE.match(raw)
            if not match:
                return found
            found.add(match.group(1))
            raw = match.group(2)
            continue
        name = _qualifier_name(raw)
        if name is None:
            return found
        found.add(name)
        raw = typing.get_args(raw)[0]


def _strip_qualifiers(hint: Any) -> Any:
    while _qualifier_name(hint) is not None:
        hint = typing.get_args(hint)[0]
    return hint


def _qualified(text: str, qualifiers: list[str]) -> str:
    for name in reversed(qualifiers):
        text = f"{name}[{text}]"
    return text


def emit_typeddict_stub(cls: type, ctx: StubContext) -> str:
    """Return ``class Name(TypedDict[, total=False]):`` with one line per field.

    Fields whose requiredness differs from the class's ``total`` are written
    ``Required[...]`` / ``NotRequired[...]``, and read-only ones ``ReadOnly[...]``.
    """
    total = getattr(cls, "__total__", True)
    suffix = ", total=False" if not total else ""
    lines = [f"class {cls.__name__}(TypedDict{suffix}):"]

    raw = get_own_annotations(cls)
    try:
        ann = typing.get_type_hints(cls)
    except Exception:
        ann = raw
    if not ann:
        lines.append("    ...")
        return "\n".join(lines)

    required = getattr(cls, "__required_keys__", frozenset())
    optional = getattr(cls, "__optional_keys__", frozenset())
    readonly = getattr(cls, "__readonly_keys__", frozenset())
    for field_name, field_type in ann.items():
        explicit = _raw_qualifiers(raw.get(field_name))
        qualifiers: list[str] = []
        if "Required" in explicit or "NotRequired" in explicit:
            qualifiers.extend(q for q in ("Required", "NotRequired") if q in explicit)
        elif total and field_name in optional:
            qualifiers.append("NotRequired")
        elif not total and field_name in required:
            qualifiers.append("Required")
        if "ReadOnly" in explicit or field_name in readonly:
            qualifiers.append("ReadOnly")
        text = _qualified(annotation_to_str(_strip_qualifiers(field_type), ctx), qualifiers)
        lines.append(f"    {field_name}: {text}")

    return "\n".join(lines)
