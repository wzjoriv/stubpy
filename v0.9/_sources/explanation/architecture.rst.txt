Architecture
============

Every stage up to :class:`~stubpy.StubResult` is a pure function of its inputs. Only the last
step touches the disk. That is why ``render`` can return text without writing anything and
``check`` can compare without changing a file.

Data flow
---------

.. mermaid::

   flowchart TB
       subgraph IN["Targets"]
           PY[".py file / package folder"]
           MOD["dotted module name"]
           EXT["compiled .pyd / .so"]
       end
       subgraph LOAD["analysis.loader"]
           IMP["package-aware import<br/>root on sys.path, restore after"]
           SRC["source text when available"]
       end
       PY --> IMP & SRC
       MOD --> IMP
       EXT --> IMP
       SRC --> HV["analysis.harvest<br/>AST pre-pass: defs, decorators,<br/>forwarding calls, __all__, literals"]
       IMP --> LIVE["live module objects"]
       LIVE --> CMP["compiled.signatures<br/>text sig / pybind11 / nanobind / Cython"]
       HV --> ST["analysis.symbols<br/>SymbolTable"]
       LIVE --> ST
       CMP --> ST
       ST --> RS["resolve<br/>**kwargs / *args back-tracing<br/>MRO, cls(), self.m(), functions"]
       RS --> EM["emit<br/>classes, functions, variables,<br/>aliases, overloads, special classes"]
       EM --> HD["core.header<br/>typing / cross-module imports"]
       HD --> RES[("StubResult<br/>text + diagnostics")]
       RES --> OUT{"core.pipeline"}
       OUT -->|generate| W["write .pyi"]
       OUT -->|incremental| M["merge into existing .pyi"]
       OUT -->|check| C["stale-stub report"]
       OUT -->|render| P["return text"]
       CFG["config<br/>Config / pyproject"] -.-> LOAD & RS & EM & OUT
       HINT["hint decorators<br/>stubpy.hint.signature / ignore"] -.-> ST

Compiled modules (``EXT``) take the ``compiled.signatures`` path: signatures come from the
binding tool's metadata instead of source; see :doc:`../guides/compiled`.

How a stub is built
-------------------

#. **Resolve targets.** Files, folders, globs and dotted names become a list of modules;
   folders skip the excluded paths (see :doc:`../guides/configuration`).
   Modules are grouped by their import root so each group loads against the right
   ``sys.path``.
#. **Load.** Unless the import policy forbids it, the module is imported with its package
   root on ``sys.path`` (restored afterwards). A ``sys.meta_path`` guard refuses modules the
   policy (``imports``, ``deny_imports``) does not allow, and is removed afterwards. If the
   import fails, that module continues from the source alone, with a WARNING; if the policy
   blocks it, with an INFO. The source is always read.
#. **Harvest.** An AST pass records definitions, decorators, ``__all__``, literal values,
   hints and the calls that forward ``**kwargs`` / ``*args``.
#. **Symbol table.** Live objects and harvested facts are merged per symbol and per parameter into one
   :class:`~stubpy.extend.SymbolTable` of classes, functions, variables, aliases and
   overload groups.
#. **Resolve parameters.** For each signature that takes ``**kwargs`` or ``*args``, the
   forwarding target is found (MRO, ``cls(...)``, ``self.method(...)``, a function) and its
   parameters are merged in. See :doc:`../guides/forwarding`.
#. **Emit.** Each symbol is written as stub text: classes (with dedicated forms for
   dataclasses, enums, ``TypedDict`` and ``NamedTuple``), functions, variables, aliases and
   overloads.
#. **Header.** The ``typing`` and cross-module imports the text needs are added at the top.
#. **Result.** Text and diagnostics are returned as a :class:`~stubpy.StubResult`.
#. **Write, merge or compare.** ``generate`` writes the file. With ``incremental`` the text
   is first merged into the existing stub. ``check`` compares it with the file on disk.

Sub-package map
---------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Package
     - Contents
   * - ``stubpy.config``
     - ``Config`` (``options``) and its choices ``UnionStyle``, ``AliasStyle``,
       ``VersionBranches`` (``_choices``); finding and loading ``stubpy.toml`` /
       ``[tool.stubpy]`` (``files``).
   * - ``stubpy.state``
     - The run state every later layer shares: the run context (``context``) and the
       diagnostics it collects (``diagnostics``, ``_diagnostic_types``).
   * - ``stubpy.analysis``
     - The loader (``loader`` with ``_module_loader`` and ``_load_errors``), the AST
       ``harvest`` pass and its records (``harvest.models``, ``_part_models``,
       ``_module_models``), import scanning, aliases, hints, the symbol table (``symbols``)
       and docstring type inference (``docstrings``).
   * - ``stubpy.resolve``
     - ``**kwargs`` / ``*args`` back-tracing: callable introspection (``callables``,
       ``_cached_facts``), the MRO walk, ``cls(...)`` calls, parameter merging, and the
       source-only resolver (``static``).
   * - ``stubpy.emit``
     - Stub text for classes, functions, variables, aliases and overloads; signature assembly
       (``signature``, ``_def_layout``, ``_variadic_notes``); source-only classes
       (``ast_only``, ``_ast_params``, ``_ast_branches``); the annotation handler registry;
       special-class forms.
   * - ``stubpy.core``
     - Results, target resolution (``targets``, ``_target_models``, ``_target_specs``), the
       pipeline and the public ``render`` / ``generate`` / ``check`` (``api``, ``_output``).
       ``core.context`` and ``core.diagnostics`` remain as aliases of their ``stubpy.state``
       modules.
   * - ``stubpy.cli``
     - The ``stubpy`` command.
   * - ``stubpy.compiled``
     - Compiled-module support: detection, runtime introspection, binding-tool signatures,
       C API and Cython sources, docstring sync.
   * - ``stubpy.merge``
     - Incremental-update markers; ``_merge_regions`` finds the generated regions of a stub.
   * - ``stubpy.hint``, ``stubpy.extend``
     - The user-facing decorators and the advanced namespace.

Constants live next to their users: ``stubpy._constants`` holds the ones shared by several
sub-packages (and the ones ``stubpy.hint`` needs), and each sub-package keeps its own in a
private ``_constants`` module.

Layering rules
--------------

Dependencies flow one way: ``config`` → ``state`` → ``analysis`` → ``resolve`` → ``emit`` → ``core`` →
``cli``. ``compiled`` sits beside ``analysis`` and ``resolve``: the two may import each other,
and neither imports ``emit``, ``core`` or ``cli``.

* A module or sub-package whose name starts with ``_`` belongs to its parent package only.
  Anything another package imports has a public name.
* A package never imports a later one. The run state (``state``) sits directly above
  ``config`` so that every later layer can share one context and one diagnostic collector.
* ``config`` imports no other sub-package.
* The user API is re-exported from ``stubpy/__init__.py`` with ``__all__``.

``tests/test_package_boundaries.py`` and ``tests/test_package_exports.py`` check these
rules.
