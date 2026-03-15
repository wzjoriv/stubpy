.. _api_context:

stubpy.context
==============

.. automodule:: stubpy.context
   :no-members:

.. autoclass:: stubpy.context.StubContext
   :members:
   :special-members: __init__
   :show-inheritance:

.. autoclass:: stubpy.context.AliasEntry
   :members:
   :show-inheritance:

.. rubric:: Notes

:class:`StubContext` replaces the three module-level globals present in
earlier versions of stubpy (``_ALIAS_REGISTRY``, ``_USED_TYPE_IMPORTS``,
``_TYPE_MODULE_IMPORTS``).  Each call to
:func:`~stubpy.generator.generate_stub` creates a fresh instance, making
the generator fully re-entrant.

The most useful method for callers is :meth:`StubContext.lookup_alias`,
which checks the registry and marks the matching module as used in the
same step.
