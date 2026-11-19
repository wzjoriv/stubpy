"""Signatures from nanobind metadata, ``inspect`` and docstrings, best source first."""
from __future__ import annotations

import enum
import inspect
import re
from typing import Any

from ._text import default_text, normalize_type
from .models import Param, Signature
from .parse import docstring_signatures, parse_signature

__all__ = ["nanobind_signatures", "from_inspect", "signatures_of", "class_signatures"]

_NB_PLACEHOLDER = re.compile(r"\\(\d+)")


def nanobind_signatures(obj: Any) -> list[Signature]:
    """Signatures from nanobind's ``__nb_signature__``."""
    entries = getattr(obj, "__nb_signature__", None)
    if not entries:
        return []
    found: list[Signature] = []
    for entry in entries:
        text = entry[0] if isinstance(entry, tuple) else entry
        defaults = entry[2] if isinstance(entry, tuple) and len(entry) > 2 and entry[2] else ()

        def fill(m: re.Match[str], defaults: tuple = defaults) -> str:
            idx = int(m.group(1))
            if idx < len(defaults):
                return value_text(defaults[idx])
            return "..."

        parsed = parse_signature(_NB_PLACEHOLDER.sub(fill, text))
        if parsed:
            found.append(parsed[1])
    return found


def value_text(value: Any) -> str:
    """Default text for a live value; an enum member is qualified by its module (``pkg._ext.Mode.FAST``)."""
    if isinstance(value, enum.Enum):
        cls = type(value)
        try:
            exact = cls[value.name] is value
        except (KeyError, TypeError):
            exact = False
        if exact and "<" not in cls.__qualname__:
            return f"{cls.__module__}.{cls.__qualname__}.{value.name}"
    return default_text(repr(value))


def from_inspect(sig: inspect.Signature) -> Signature:
    """Convert an ``inspect.Signature`` (annotations as text when they are strings)."""
    params = []
    for p in sig.parameters.values():
        ann = p.annotation if isinstance(p.annotation, str) else None
        default = None if p.default is inspect.Parameter.empty else value_text(p.default)
        params.append(Param(p.name, p.kind, normalize_type(ann), default))
    ret = sig.return_annotation if isinstance(sig.return_annotation, str) else None
    return Signature(tuple(params), normalize_type(ret))


def signatures_of(obj: Any, name: str | None = None) -> list[Signature]:
    """Best available signatures of a compiled callable: nanobind, then docstring, then ``inspect``."""
    name = name or getattr(obj, "__name__", "")
    found = nanobind_signatures(obj)
    if found:
        return found
    doc_sigs = docstring_signatures(name, getattr(obj, "__doc__", None))
    try:
        insp = from_inspect(inspect.signature(obj))
    except (TypeError, ValueError):
        insp = None
    useful = [s for s in doc_sigs if not s.is_generic()]
    if insp is not None and not insp.is_generic() and insp.returns is None and len(doc_sigs) == 1:
        doc = doc_sigs[0]
        if doc.returns and _untyped(doc) and (doc.is_generic() or _same_names(doc, insp)):
            return [Signature(insp.params, doc.returns)]
    if useful:
        return useful
    if insp is not None and not insp.is_generic():
        return [insp]
    return []


def _untyped(sig: Signature) -> bool:
    """True when no parameter of *sig* is annotated (a C API ``name(a, b) -> R`` line)."""
    return not any(p.annotation for p in sig.params)


def _same_names(a: Signature, b: Signature) -> bool:
    """True when *a* and *b* name the same parameters, receivers ignored."""
    return [n for n in a.names if n not in ("self", "cls")] == [n for n in b.names if n not in ("self", "cls")]


def class_signatures(cls: type) -> list[Signature]:
    """Constructor signatures written on the class itself: ``__text_signature__`` or ``Name(...)`` in its doc."""
    if getattr(cls, "__text_signature__", None):
        try:
            return [from_inspect(inspect.signature(cls))]
        except (TypeError, ValueError):
            pass
    return [s for s in docstring_signatures(cls.__name__, cls.__doc__) if not s.is_generic()]
