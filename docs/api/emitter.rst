.. _api_emitter:

stubpy.emitter
==============

.. automodule:: stubpy.emitter
   :no-members:

.. rubric:: Class stubs

.. autofunction:: stubpy.emitter.generate_class_stub
.. autofunction:: stubpy.emitter.generate_method_stub
.. autofunction:: stubpy.emitter.methods_defined_on

.. rubric:: Module-level symbol stubs

.. autofunction:: stubpy.emitter.generate_function_stub
.. autofunction:: stubpy.emitter.generate_variable_stub
.. autofunction:: stubpy.emitter.generate_alias_stub
.. autofunction:: stubpy.emitter.generate_overload_group_stub

.. rubric:: Parameter helpers

.. autofunction:: stubpy.emitter.insert_kw_separator
.. autofunction:: stubpy.emitter.insert_pos_separator

.. rubric:: Formatting rules

**Inline** (≤ 2 non-self/cls parameters)::

    def area(self) -> float: ...
    def scale(self, sx: float, sy: Optional[float] = None) -> Element: ...

**Multi-line** (> 2 non-self/cls parameters), each param on its own line
with a trailing comma::

    def __init__(
        self,
        width: float,
        height: float,
        depth: float = 1.0,
    ) -> None: ...

Trailing commas make diffs cleaner — adding or removing a parameter
changes exactly one line.

.. rubric:: Positional-only separator

When a function declares positional-only parameters (PEP 570), a bare ``/``
is inserted after the last positional-only parameter::

    def move(x: float, y: float, /, z: float = 0.0) -> None: ...

:func:`insert_pos_separator` manages this, mirroring how
:func:`insert_kw_separator` manages the ``*`` separator.

.. rubric:: TypeVar and Generic stubs

TypeVar, TypeAlias, NewType, ParamSpec, and TypeVarTuple declarations are
re-emitted verbatim from the AST pre-pass via :func:`generate_alias_stub`,
preserving bounds, constraints, and alias right-hand sides.

Generic base classes use ``__orig_bases__`` (PEP 560) instead of ``__bases__``
so subscripts like ``Generic[T]`` and ``Generic[K, V]`` are preserved exactly.

.. rubric:: @overload stubs

When a module declares ``@overload``-decorated functions, each variant
gets its own stub and the concrete implementation is suppressed, per PEP 484::

    @overload
    def parse(x: int) -> int: ...

    @overload
    def parse(x: str) -> str: ...

.. rubric:: Public dunders

Only the methods listed in the internal ``_PUBLIC_DUNDERS`` set are
included in stubs. Internal Python machinery names (``__dict__``,
``__weakref__``, ``__class__``, etc.) are omitted.
