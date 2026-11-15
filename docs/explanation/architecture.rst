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

#. **Resolve targets.** Files, folders, globs and dotted names become a list of modules.
   Modules are grouped by their import root so each group loads against the right
   ``sys.path``.
#. **Load.** In ``runtime`` mode the module is imported with its package root on
   ``sys.path`` (restored afterwards). In ``ast`` mode only the source is read.
#. **Harvest.** An AST pass records definitions, decorators, ``__all__``, literal values,
   hints and the calls that forward ``**kwargs`` / ``*args``.
#. **Symbol table.** Live objects and harvested facts are merged into one
   :class:`~stubpy.extend.SymbolTable` of classes, functions, variables, aliases and
   overload groups.
#. **Resolve parameters.** For each signature that takes ``**kwargs`` or ``*args``, the
   forwarding target is found (MRO, ``cls(...)``, ``self.method(...)``, a function) and its
   parameters are merged in. See :doc:`../guides/kwargs`.
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
     - ``Config``, ``Mode``, ``UnionStyle``, ``AliasStyle``; finding and loading
       ``stubpy.toml`` / ``[tool.stubpy]``.
   * - ``stubpy.core``
     - The run context, diagnostics, results, target resolution, the pipeline and the public
       ``render`` / ``generate`` / ``check``.
   * - ``stubpy.analysis``
     - The loader, the AST ``harvest`` pass, import scanning, aliases, hints, the symbol table
       (``symbols``) and docstring type inference (``docstrings``).
   * - ``stubpy.resolve``
     - ``**kwargs`` / ``*args`` back-tracing: the MRO walk, ``cls(...)`` calls, parameter
       merging.
   * - ``stubpy.emit``
     - Stub text for classes, functions, variables, aliases and overloads; the annotation
       handler registry; special-class forms.
   * - ``stubpy.merge``
     - Incremental-update markers.
   * - ``stubpy.hint``, ``stubpy.extend``
     - The user-facing decorators and the advanced namespace.
   * - ``stubpy.cli``
     - The ``stubpy`` command.
   * - ``stubpy.compiled``
     - Compiled-module support (in progress).

Layering rules
--------------

* A module or sub-package whose name starts with ``_`` belongs to its parent package only.
  Anything another package imports has a public name.
* ``analysis`` and ``resolve`` never import ``emit``, ``core.pipeline`` or ``core.api``.
* ``emit`` never imports ``core.pipeline`` or ``core.api``.
* The user API is re-exported from ``stubpy/__init__.py`` with ``__all__``.

``tests/test_package_boundaries.py`` and ``tests/test_package_exports.py`` check these
rules.
