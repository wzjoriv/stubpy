"""
Signatures of compiled callables from text signatures, binding docstrings and nanobind metadata.
"""
from __future__ import annotations

from ._text import ANY_ARRAY, C_TYPES, matching_paren, normalize_type, split_top
from .models import Param, Signature
from .parse import docstring_signatures, parse_signature, strip_signature_lines
from .sources import class_signatures, from_inspect, nanobind_signatures, signatures_of

__all__ = [
    "ANY_ARRAY",
    "C_TYPES",
    "Param",
    "class_signatures",
    "Signature",
    "docstring_signatures",
    "from_inspect",
    "nanobind_signatures",
    "matching_paren",
    "normalize_type",
    "parse_signature",
    "signatures_of",
    "split_top",
    "strip_signature_lines",
]
