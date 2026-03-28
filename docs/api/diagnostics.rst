.. _api_diagnostics:

stubpy.diagnostics
==================

.. automodule:: stubpy.diagnostics
   :no-members:

.. autoclass:: stubpy.diagnostics.DiagnosticLevel
   :members:
   :undoc-members:

.. autoclass:: stubpy.diagnostics.DiagnosticStage
   :members:
   :undoc-members:

.. autoclass:: stubpy.diagnostics.Diagnostic
   :members:
   :special-members: __str__

.. autoclass:: stubpy.diagnostics.DiagnosticCollector
   :members:

.. rubric:: Notes

A fresh :class:`DiagnosticCollector` is created inside every
:class:`~stubpy.context.StubContext`.  Pipeline stages call
:meth:`~DiagnosticCollector.info`, :meth:`~DiagnosticCollector.warning`,
or :meth:`~DiagnosticCollector.error` rather than swallowing exceptions
silently.

:class:`Diagnostic` is a frozen :func:`~dataclasses.dataclass`, so
instances are immutable and hashable.

The ``--verbose`` CLI flag prints :meth:`~DiagnosticCollector.format_all`
to ``stderr`` after the run.  The ``--strict`` flag causes ``sys.exit(1)``
when :meth:`~DiagnosticCollector.has_errors` returns ``True``.
