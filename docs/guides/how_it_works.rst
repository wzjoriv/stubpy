.. _how_it_works:

How it works
============

stubpy is a pipeline of six focused stages.  Each stage is a separate
module with a single responsibility, and all mutable run-state is held in
a :class:`~stubpy.context.StubContext` that is created fresh for every
call to :func:`~stubpy.generator.generate_stub`.

.. code-block:: text

   generate_stub(filepath)
       │
       ├─ 1. loader     load_module()            → module, path
       ├─ 2. imports    scan_import_statements() → import_map
       ├─ 3. aliases    build_alias_registry()   → ctx populated
       ├─ 4. generator  collect_classes()        → sorted class list
       │       └─ for each class:
       │           emitter  generate_class_stub()
       │               └─ for each method:
       │                   resolver  resolve_params()
       │                   emitter   generate_method_stub()
       └─ 5. generator  assemble header + body → write .pyi

Stage 1 — Module loading
------------------------

:mod:`stubpy.loader` uses :func:`importlib.util.spec_from_file_location`
to load the source file as a live Python module.  The file's parent
directory *and* its grandparent are temporarily added to :data:`sys.path`
so that package-relative imports inside the target file resolve correctly,
then removed once loading completes.

Stage 2 — Import scanning
--------------------------

:mod:`stubpy.imports` parses the source AST to build a
``{local_name: import_statement}`` map of every import in the file.  This
map is used later to:

- discover type-alias sub-modules (Stage 3),
- re-emit cross-file class imports in the ``.pyi`` header (Stage 5).

Stage 3 — Alias registry
-------------------------

:mod:`stubpy.aliases` scans the loaded module for imported sub-modules
(e.g. ``from demo import types``).  Any attribute of such a sub-module
that is a type alias — a PEP 604 union (``str | int``) or a subscripted
typing generic (``List[str]``, ``Literal["a"]``) — is registered in the
:class:`~stubpy.context.StubContext`.

When :func:`~stubpy.annotations.annotation_to_str` encounters a matching
annotation later, it emits ``types.Length`` instead of expanding it to
``str | float | int``.

Stage 4 — Parameter resolution
--------------------------------

:mod:`stubpy.resolver` implements the core **kwargs/args backtracing** logic
via :func:`~stubpy.resolver.resolve_params`.  Three strategies are tried in
order:

1. **No variadics** — return the method's own parameters unchanged.

2. **@classmethod cls() detection** — if the method is a ``@classmethod``
   and its AST contains a call ``cls(..., **kwargs)``, the ``**kwargs`` is
   resolved against ``cls.__init__`` (which is itself fully resolved).
   Parameters explicitly passed in the ``cls(...)`` call are excluded from
   the stub.

3. **MRO walk** — iterate the class MRO, collecting concrete parameters
   from each ancestor that defines the same method, until no unresolved
   ``**kwargs`` or ``*args`` remain.

   Typed ``*args`` (e.g. ``*elements: Element``) always survive because
   they carry explicit annotation information that should not be discarded.

Stage 5 — Annotation conversion
---------------------------------

:mod:`stubpy.annotations` converts live annotation objects to stub-safe
strings using a *dispatch table* rather than an if/elif chain.  Each
annotation kind is handled by a small function decorated with
``@_register(predicate)``.  The alias registry is checked first, so
type-module aliases take priority over raw expansion.

Stage 6 — Emission and header assembly
---------------------------------------

:mod:`stubpy.emitter` formats each class and method into ``.pyi`` text.
Methods with ≤ 2 non-self parameters stay on one line; longer signatures
are split across lines with a trailing comma on each parameter for clean
diffs.

:mod:`stubpy.generator` then assembles the file header:

- ``from __future__ import annotations``
- ``from typing import ...`` (only the names actually used)
- Type-module imports for aliases that were referenced
- Cross-file class imports for base classes / annotation types
