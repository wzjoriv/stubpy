"""Signatures of compiled callables from text signatures, binding docstrings and nanobind metadata."""
from __future__ import annotations

from ._text import C_TYPES, normalize_type
from .models import Param, Signature
from .parse import docstring_signatures, parse_signature, strip_signature_lines
from .sources import class_signatures, from_inspect, nanobind_signatures, signatures_of

__all__ = [
    "C_TYPES",
    "Param",
    "class_signatures",
    "Signature",
    "docstring_signatures",
    "from_inspect",
    "nanobind_signatures",
    "normalize_type",
    "parse_signature",
    "signatures_of",
    "strip_signature_lines",
]
