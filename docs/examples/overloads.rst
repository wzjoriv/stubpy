.. _examples_overloads:

Overloads and TypeVar
======================

stubpy correctly handles ``@overload`` decorated functions and generic
TypeVar declarations.

``@overload`` stubs
-------------------

Per PEP 484, a stub should contain one ``@overload`` entry per variant
and suppress the concrete implementation.  stubpy does this automatically
by grouping overloads detected during the AST pre-pass:

.. code-block:: python

    from typing import overload

    @overload
    def parse(value: str) -> str: ...
    @overload
    def parse(value: int) -> int: ...
    def parse(value):
        return value   # concrete implementation

Generated stub — the concrete ``def parse(value)`` is suppressed:

.. code-block:: python

    @overload
    def parse(value: str) -> str: ...

    @overload
    def parse(value: int) -> int: ...

Three-variant overload
----------------------

.. code-block:: python

    @overload
    def scale(v: int,   f: int)   -> int:   ...
    @overload
    def scale(v: float, f: float) -> float: ...
    @overload
    def scale(v: str,   f: int)   -> str:   ...
    def scale(v, f): return v * f

Generated stub:

.. code-block:: python

    @overload
    def scale(v: int, f: int) -> int: ...

    @overload
    def scale(v: float, f: float) -> float: ...

    @overload
    def scale(v: str, f: int) -> str: ...

Overloaded classmethod
----------------------

.. code-block:: python

    class Converter:
        @classmethod
        @overload
        def from_str(cls, raw: str, *, radix: int) -> "Converter[int]": ...
        @classmethod
        @overload
        def from_str(cls, raw: str) -> "Converter[str]": ...
        @classmethod
        def from_str(cls, raw, **kwargs): ...

Generated stub:

.. code-block:: python

    class Converter:
        @classmethod
        @overload
        def from_str(cls, raw: str, *, radix: int) -> Converter[int]: ...

        @classmethod
        @overload
        def from_str(cls, raw: str) -> Converter[str]: ...

TypeVar declarations
--------------------

TypeVar, ParamSpec, TypeVarTuple, and NewType declarations are
re-emitted verbatim from the AST pre-pass — the runtime objects are
never converted to strings (which would produce ``~T`` on Python 3.12+):

.. code-block:: python

    from typing import TypeVar, ParamSpec, NewType

    T  = TypeVar("T")
    P  = ParamSpec("P")
    Nd = TypeVar("Nd", int, float)          # constrained TypeVar
    Db = TypeVar("Db", bound="Drawable")    # bound TypeVar

    UserId = NewType("UserId", int)

Generated stub:

.. code-block:: python

    from typing import NewType, ParamSpec, TypeVar

    T  = TypeVar('T')
    P  = ParamSpec('P')
    Nd = TypeVar('Nd', int, float)
    Db = TypeVar('Db', bound='Drawable')

    UserId = NewType('UserId', int)

TypeAlias
---------

All TypeAlias forms are detected and preserved:

.. code-block:: python

    from typing import TypeAlias

    # Explicit PEP 613
    Pixels: TypeAlias = int
    Color:  TypeAlias = tuple[float, float, float, float]

    # Implicit (bare union / subscripted generic)
    Length = int | float | str
    Matrix = list[list[float]]

    # Python 3.12+ PEP 695
    # type Vector = list[float]   (emitted as-is when alias_style="pep695")

Generated stub (``alias_style="compatible"``, the default):

.. code-block:: python

    from typing import TypeAlias

    Pixels: TypeAlias = int
    Color:  TypeAlias = tuple[float, float, float, float]
    Length: TypeAlias = int | float | str
    Matrix: TypeAlias = list[list[float]]
