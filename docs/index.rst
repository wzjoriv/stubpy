.. stubpy documentation root

stubpy
======

.. raw:: html

   <div class="hero-block">
   <strong>stubpy</strong> generates <code>.pyi</code> stub files for Python modules
   with full <code>**kwargs</code> / <code>*args</code> MRO backtracing,
   type-alias preservation, and cross-file import resolution.
   </div>

**Key features**

- **kwargs backtracing** — walks the entire MRO to expand ``**kwargs`` into
  concrete, named parameters at every inheritance level.
- **cls() detection** — ``@classmethod`` methods that forward ``**kwargs``
  into ``cls(...)`` are resolved against ``cls.__init__``, not the MRO.
- **Typed \*args preserved** — explicitly annotated ``*args`` (e.g.
  ``*elements: Element``) always survive the resolution chain.
- **Type-alias preservation** — ``types.Length`` stays ``types.Length``
  rather than expanding to ``str | float | int``.  Preserved inside
  ``Optional[...]``, ``tuple[...]``, ``list[...]``, and mixed ``Union``
  forms via the AST pre-pass.
- **Cross-file imports** — base classes and annotation types from other
  local modules are re-emitted in the ``.pyi`` header automatically.
- **Structured diagnostics** — every pipeline stage records ``INFO``,
  ``WARNING``, and ``ERROR`` entries rather than swallowing exceptions
  silently.  Use ``--verbose`` to inspect them and ``--strict`` to enforce
  clean runs.
- **Zero dependencies** — stdlib only at runtime.

----

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   guides/installation
   guides/quickstart
   guides/how_it_works

.. toctree::
   :maxdepth: 2
   :caption: Examples

   examples/basic
   examples/kwargs_backtracing
   examples/type_aliases
   examples/cross_file

.. toctree::
   :maxdepth: 3
   :caption: API Reference

   api/index

.. toctree::
   :maxdepth: 1
   :caption: Project

   changelog
