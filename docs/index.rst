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
- **Typed \\*args preserved** — explicitly annotated ``*args`` always survive
  the resolution chain.
- **Positional-only ``/`` separator** — PEP 570 positional-only parameters are
  emitted correctly; pos-only params absorbed by ``**kwargs`` are promoted to
  ``POSITIONAL_OR_KEYWORD`` to keep the child stub valid.
- **TypeVar / Generic / overload** — TypeVar, TypeAlias, NewType, ParamSpec,
  and TypeVarTuple declarations are re-emitted.  ``Generic[T]`` bases are
  preserved via ``__orig_bases__``.  ``@overload`` variants each get their own
  stub; the concrete implementation is suppressed per PEP 484.
- **Type alias detection** — explicit ``Name: TypeAlias = ...``, bare PEP 604
  unions ``Name = int | float``, subscripted generics, known built-in type
  names, and Python 3.12+ ``type Name = ...`` (PEP 695) are all detected.
- **Type-alias preservation** — ``types.Length`` stays ``types.Length`` rather
  than expanding to ``str | float | int``.
- **Cross-file imports** — base classes and annotation types from other local
  modules are re-emitted in the ``.pyi`` header automatically.
- **``# stubpy: ignore``** — place this comment at the top of any source file
  to exclude it from stub generation entirely.
- **Package batch generation** — :func:`~stubpy.generator.generate_package`
  recursively stubs a whole directory tree with a single call.
- **Configuration file** — ``stubpy.toml`` or ``[tool.stubpy]`` in
  ``pyproject.toml`` controls all options; CLI flags override file values.
- **Typing style** — ``"modern"`` (``X | None``) or ``"legacy"``
  (``Optional[X]``) output; ``type_alias_style`` selects between
  ``compatible`` (``Name: TypeAlias = ...``) and ``pep695`` (``type Name = ...``).
- **Execution modes** — ``RUNTIME``, ``AST_ONLY``, or ``AUTO``.
- **Structured diagnostics** — every pipeline stage records ``INFO``,
  ``WARNING``, and ``ERROR`` entries.  Use ``--verbose`` / ``--strict``.
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
   :maxdepth: 1
   :caption: API Reference

   api/public
   api/index

.. toctree::
   :maxdepth: 1
   :caption: Project

   changelog
   GitHub repository <https://github.com/wzjoriv/stubpy>
