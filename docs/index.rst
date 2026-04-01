.. stubpy documentation root

stubpy
======

.. raw:: html

   <div class="hero-block">
   <strong>stubpy</strong> generates <code>.pyi</code> stub files for Python modules
   with full <code>**kwargs</code> / <code>*args</code> MRO backtracing,
   type-alias preservation, Generic support, overload stubs, and cross-file import resolution.
   </div>

**Key features**

- **kwargs backtracing** — walks the entire MRO to expand ``**kwargs`` into
  concrete, named parameters at every inheritance level.
- **cls() detection** — ``@classmethod`` methods that forward ``**kwargs``
  into ``cls(...)`` are resolved against ``cls.__init__``, not the MRO.
- **Typed \\*args preserved** — explicitly annotated ``*args`` (e.g.
  ``*elements: Element``) always survive the resolution chain.
- **Positional-only ``/`` separator** — PEP 570 ``def f(a, b, /, c)``
  produces the correct ``/`` in the stub; pos-only params absorbed by
  ``**kwargs`` are promoted to ``POSITIONAL_OR_KEYWORD``.
- **TypeVar / Generic / overload** — ``TypeVar``, ``TypeAlias``, ``NewType``,
  ``ParamSpec``, and ``TypeVarTuple`` declarations are re-emitted verbatim.
  ``Generic[T]`` bases are preserved via ``__orig_bases__``.  ``@overload``
  variants each get their own stub; the implementation is suppressed.
- **Type-alias preservation** — ``types.Length`` stays ``types.Length``
  rather than expanding to ``str | float | int``.  Works inside
  ``Optional[...]``, ``tuple[...]``, ``list[...]``, and mixed unions.
- **Cross-file imports** — base classes and annotation types from other
  local modules are re-emitted in the ``.pyi`` header automatically.
- **Package batch generation** — :func:`~stubpy.generator.generate_package`
  recursively stubs a whole directory tree, mirrors the structure, and creates
  ``__init__.pyi`` markers for every sub-package.
- **Configuration file** — ``stubpy.toml`` or ``[tool.stubpy]`` in
  ``pyproject.toml`` controls all options; CLI flags override file values.
- **Typing style** — choose ``"modern"`` (``X | None``, PEP 604, default) or
  ``"legacy"`` (``Optional[X]``) output.
- **Execution modes** — ``RUNTIME`` (default), ``AST_ONLY`` (no module
  execution), ``AUTO`` (runtime with graceful fallback).
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
   examples/project_integration

.. toctree::
   :maxdepth: 3
   :caption: API Reference

   api/index

.. toctree::
   :maxdepth: 1
   :caption: Project

   changelog
