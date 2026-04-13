.. stubpy documentation root

stubpy
======

**stubpy** generates ``.pyi`` stub files for Python modules — complete with
full ``**kwargs`` / ``*args`` MRO backtracing, type-alias preservation,
Generic and overload support, and cross-file import resolution.

.. code-block:: bash

    pip install stubpy
    stubpy mymodule.py          # → mymodule.pyi
    stubpy mypackage/           # → stubs entire package tree

.. rubric:: Why stubpy?

Most stub generators leave ``**kwargs`` as ``**kwargs``.  stubpy *walks* the
entire class MRO to expand ``**kwargs`` into the concrete named parameters
that the method actually accepts — giving IDEs full auto-complete even across
deep inheritance hierarchies.

.. rubric:: At a glance

.. list-table::
   :widths: 40 60
   :header-rows: 0

   * - ``**kwargs`` backtracing
     - Walks MRO to emit every concrete kwarg, including pos-only promotion
   * - Function-level forwarding
     - Module-level functions that forward ``**kwargs`` are also expanded
   * - TypeVar / Generic / overload
     - TypeVar, TypeAlias, NewType, Generic[T], @overload all preserved
   * - TypedDict / Enum / dataclass
     - Dedicated clean stubs for every special class form
   * - Type-alias preservation
     - ``types.Length`` stays ``types.Length``, not ``str | float | int``
   * - Cross-file imports
     - Base-class and annotation imports auto-added to the .pyi header
   * - Package batch generation
     - One call stubs an entire directory tree
   * - Custom annotation handlers
     - Extend the dispatch table with ``register_annotation_handler()``
   * - Zero runtime dependencies
     - stdlib only

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
   examples/mro_backtracing
   examples/special_classes
   examples/overloads
   examples/type_aliases
   examples/extending
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
