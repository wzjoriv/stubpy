.. _api_imports:

stubpy.imports
==============

.. automodule:: stubpy.imports
   :no-members:

.. autofunction:: stubpy.imports.scan_import_statements
.. autofunction:: stubpy.imports.collect_typing_imports
.. autofunction:: stubpy.imports.collect_cross_imports
.. autofunction:: stubpy.imports.collect_special_imports

.. rubric:: Import scanning

:func:`scan_import_statements` uses :func:`ast.parse` on the raw source
text rather than inspecting the loaded module.  This means it captures all
imports — including inline ones inside function bodies — and works even when
some imports fail to resolve at runtime.

Star imports (``from module import *``) are recorded under the reserved key
``"*"`` so callers can detect and handle them explicitly.

.. rubric:: Typing candidates

:func:`collect_typing_imports` scans ``typing.__all__`` at import time to
build its candidate set.  This means it automatically covers names added in
future Python releases without any code changes.  Matching uses whole-word
boundaries so ``List`` is not falsely matched inside ``BlackList``.

.. rubric:: Cross-import heuristic

:func:`collect_cross_imports` uses two regex patterns on the stub body:

1. **Base classes** — ``class \\w+\\(([^)]+)\\)``
2. **Annotation names** — capitalised words after ``": "`` or ``"-> "``

Matches are filtered against the import map, stdlib prefixes, and names
defined in the module being stubbed.
