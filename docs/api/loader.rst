.. _api_loader:

stubpy.loader
=============

.. automodule:: stubpy.loader
   :no-members:

.. autofunction:: stubpy.loader.load_module

.. rubric:: sys.path management

:func:`load_module` temporarily adds two directories to :data:`sys.path`:

- The file's own parent directory (e.g. ``mypackage/shapes/``)
- The grandparent directory (e.g. ``mypackage/``)

This lets files in a sub-package do ``from mypackage import types``
without requiring the package to be installed.  Both paths are removed in
a ``finally`` block — the caller's :data:`sys.path` is always restored.

.. rubric:: Module naming

The synthetic module name has the form ``_stubpy_target_<stem>`` where
``<stem>`` is the source filename without extension.  This is unlikely to
collide with real module names and is deterministic across runs.
