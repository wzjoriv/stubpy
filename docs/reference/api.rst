Public API
==========

Everything here is importable from the top-level ``stubpy`` package.

.. currentmodule:: stubpy

.. autosummary::

   render
   generate
   check
   load_config
   sync_docstrings
   Config
   Mode
   StubResult
   Report
   Diagnostic
   Level
   hint

Functions
---------

.. autofunction:: render

.. autofunction:: generate

.. autofunction:: check

.. autofunction:: load_config

.. autofunction:: sync_docstrings

Configuration
-------------

.. autoclass:: Config
   :members: from_dict, replace
   :member-order: bysource

.. autoclass:: Mode
   :members:
   :undoc-members:

The style enums are not exported at the top level; import them from ``stubpy.config`` when
needed:

.. autoclass:: stubpy.config.UnionStyle
   :members:
   :undoc-members:

.. autoclass:: stubpy.config.AliasStyle
   :members:
   :undoc-members:

.. autoclass:: stubpy.config.VersionBranches
   :members:
   :undoc-members:

Results
-------

.. autoclass:: StubResult
   :members: ok, errors, warnings

.. autoclass:: Report
   :members: failed, ok, summary

Diagnostics
-----------

.. autoclass:: Level
   :members:
   :undoc-members:

.. autoclass:: Diagnostic

Hints
-----

.. automodule:: stubpy.hint
   :members: signature, returns, ignore
