.. _examples_special_classes:

Special class forms
===================

stubpy generates clean, correct stubs for every major Python class pattern.
This page shows what each form produces.

NamedTuple
----------

Fields are emitted in declaration order with type annotations.  Any extra
methods (``@property``, custom helpers) are preserved; auto-generated
internals (``_make``, ``_asdict``, ``_replace``) are suppressed:

.. code-block:: python

    from typing import NamedTuple

    class BoundingBox(NamedTuple):
        x: float
        y: float
        width: float
        height: float

        @property
        def right(self) -> float:
            return self.x + self.width

        def area(self) -> float:
            return self.width * self.height

Generated stub:

.. code-block:: python

    class BoundingBox(NamedTuple):
        x: float
        y: float
        width: float
        height: float

        @property
        def right(self) -> float: ...
        def area(self) -> float: ...

dataclass
---------

A synthesised ``__init__`` is built from ``__dataclass_fields__``.
``ClassVar`` fields are emitted as class annotations, not init parameters.
``default_factory`` fields show as ``field: Type = ...``:

.. code-block:: python

    from dataclasses import dataclass, field
    from typing import ClassVar

    @dataclass
    class StrokeStyle:
        color: tuple = (0.0, 0.0, 0.0, 1.0)
        width: float = 1.0
        dash_pattern: list[float] = field(default_factory=list)
        _cache: ClassVar[dict]

Generated stub:

.. code-block:: python

    @dataclass
    class StrokeStyle:
        color: tuple
        width: float
        dash_pattern: list[float]
        _cache: ClassVar[dict]

        def __init__(
            self,
            color: tuple = (0.0, 0.0, 0.0, 1.0),
            width: float = 1.0,
            dash_pattern: list[float] = ...,
        ) -> None: ...

TypedDict
---------

Emitted as ``class Name(TypedDict):`` or ``class Name(TypedDict, total=False):``.
Field annotations are pulled from ``__annotations__``:

.. code-block:: python

    from typing import TypedDict

    class RenderOptions(TypedDict, total=False):
        compact: bool
        indent: str
        dpi: float

Generated stub:

.. code-block:: python

    class RenderOptions(TypedDict, total=False):
        compact: bool
        indent: str
        dpi: float

Enum / IntEnum
--------------

The correct base class is detected (``Enum``, ``IntEnum``, ``StrEnum``, etc.)
and a ``from enum import …`` import is injected automatically.  Internal
implementation methods (``_generate_next_value_``, ``_missing_``) are
suppressed.  Enum member defaults in other classes are rendered as
``ClassName.MEMBER``, not the unreadable ``repr()``:

.. code-block:: python

    import enum

    class BlendMode(enum.Enum):
        NORMAL   = "normal"
        MULTIPLY = "multiply"
        SCREEN   = "screen"

    class Shape:
        def __init__(self, blend_mode: BlendMode = BlendMode.NORMAL): ...

Generated stubs:

.. code-block:: python

    from enum import Enum

    class BlendMode(Enum):
        def __new__(self, value) -> None: ...

    class Shape:
        # Note: BlendMode.NORMAL — not <BlendMode.NORMAL: 'normal'>
        def __init__(self, blend_mode: BlendMode = BlendMode.NORMAL): ...

Abstract base class
-------------------

``@abstractmethod`` and the ``ABC`` base class are handled:

.. code-block:: python

    from abc import ABC, abstractmethod

    class Shape(ABC):
        @abstractmethod
        def area(self) -> float: ...

        @abstractmethod
        def render(self, *, compact: bool = False) -> str: ...

        def describe(self) -> str: ...   # concrete

Generated stub:

.. code-block:: python

    from abc import ABC, abstractmethod

    class Shape(ABC):
        @abstractmethod
        def area(self) -> float: ...

        @abstractmethod
        def render(self, *, compact: bool = False) -> str: ...

        def describe(self) -> str: ...

Generic classes
---------------

``Generic[T]`` base classes are preserved via ``__orig_bases__`` (PEP 560):

.. code-block:: python

    from typing import Generic, TypeVar, Iterator

    T = TypeVar("T")

    class Stack(Generic[T]):
        def push(self, item: T) -> None: ...
        def pop(self) -> T: ...
        def __iter__(self) -> Iterator[T]: ...

Generated stub:

.. code-block:: python

    from typing import Generic, Iterator, TypeVar

    T = TypeVar('T')

    class Stack(Generic[T]):
        def push(self, item: T) -> None: ...
        def pop(self) -> T: ...
        def __iter__(self) -> Iterator[T]: ...

Protocol
--------

``@runtime_checkable`` Protocol classes are emitted correctly:

.. code-block:: python

    from typing import Protocol, runtime_checkable

    @runtime_checkable
    class Drawable(Protocol):
        def render(self, *, compact: bool = False) -> str: ...

Generated stub:

.. code-block:: python

    from typing import Protocol

    class Drawable(Protocol):
        def render(self, *, compact: bool = False) -> str: ...
