"""
Stubs for compiled extension modules (C API, Cython, pybind11, nanobind) and JIT-wrapped callables.
Importing the package loads only :mod:`~stubpy.compiled.signatures`.
"""
from __future__ import annotations

from .signatures import Param, Signature, docstring_signatures, parse_signature, signatures_of

__all__ = ["Param", "Signature", "docstring_signatures", "parse_signature", "signatures_of"]
