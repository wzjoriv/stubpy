"""
stubpy
======

Generate ``.pyi`` stub files for Python modules with full ``**kwargs``
and ``*args`` MRO backtracing.

Quickstart::

    from stubpy import generate_stub

    # Write stub alongside the source and return its content
    content = generate_stub("path/to/module.py")

    # Write to a custom path
    content = generate_stub("path/to/module.py", "out/module.pyi")

CLI::

    stubpy path/to/module.py
    stubpy path/to/module.py -o out/module.pyi --print

Public API
----------

.. currentmodule:: stubpy

.. autosummary::

    generate_stub
    StubContext
    AliasEntry
"""
from .context import AliasEntry, StubContext
from .generator import generate_stub

__all__ = ["generate_stub", "StubContext", "AliasEntry"]
__version__ = "0.1.1"
