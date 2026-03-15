.. _api_imports:

stubpy.imports
==============

.. automodule:: stubpy.imports
   :no-members:

.. autofunction:: stubpy.imports.scan_import_statements
.. autofunction:: stubpy.imports.collect_typing_imports
.. autofunction:: stubpy.imports.collect_cross_imports

.. rubric:: Import scanning

:func:`scan_import_statements` uses :func:`ast.parse` on the raw source
text rather than inspecting the loaded module.  This means it captures all
imports — including conditional ones — and works even when some imports
fail to resolve at runtime.

The candidates checked by :func:`collect_typing_imports` are:
``Any``, ``Callable``, ``ClassVar``, ``Dict``, ``FrozenSet``,
``Iterator``, ``List``, ``Literal``, ``Optional``, ``Sequence``,
``Set``, ``Tuple``, ``Type``, ``Union``.

.. rubric:: Cross-import heuristic

:func:`collect_cross_imports` uses two regex patterns on the stub body:

1. **Base classes** — ``class \\w+\\(([^)]+)\\)``
2. **Annotation names** — capitalised words after ``": "`` or ``"-> "``

Matches are filtered against the import map, stdlib prefixes, and names
defined in the module being stubbed.
