"""Stubs for compiled extension modules (C API, Cython, pybind11, nanobind) and JIT-wrapped callables.

Modules
-------
signatures
    Signature text from ``__text_signature__``, binding docstrings (pybind11
    overloads, Cython ``embedsignature``) and nanobind ``__nb_signature__``.
detect
    Extension-module files (``.pyd`` / ``.so``, ABI tags), compiled modules and callables.
typemap
    Qualified binding type names to stub annotations plus their imports.
introspect
    The :class:`~stubpy.extend.SymbolTable` of a live compiled module.
runtime
    Compiled signatures as :class:`inspect.Signature`, for ``**kwargs`` back-tracing.
docsync
    Runtime docstrings into hand-written stubs (``stubpy docstrings sync``).

Importing the package loads only :mod:`~stubpy.compiled.signatures`, so the
loader and target resolution can use :mod:`~stubpy.compiled.detect` cheaply.
"""
from __future__ import annotations

from .signatures import Param, Signature, docstring_signatures, parse_signature, signatures_of

__all__ = ["Param", "Signature", "docstring_signatures", "parse_signature", "signatures_of"]
