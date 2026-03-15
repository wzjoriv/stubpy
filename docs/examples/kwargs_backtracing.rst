.. _examples_kwargs:

\*\*kwargs and \*args backtracing
==================================

stubpy's signature feature is resolving ``**kwargs`` and typed ``*args``
into explicit parameter lists by walking the MRO.

Single-level \*\*kwargs
------------------------

.. code-block:: python
   :caption: input

   class Shape:
       def __init__(self, color: str = "black", opacity: float = 1.0) -> None: ...

   class Circle(Shape):
       def __init__(self, radius: float, **kwargs) -> None:
           super().__init__(**kwargs)

.. code-block:: python
   :caption: generated stub

   class Shape:
       def __init__(self, color: str = 'black', opacity: float = 1.0) -> None: ...

   class Circle(Shape):
       def __init__(
           self,
           radius: float,
           color: str = 'black',
           opacity: float = 1.0,
       ) -> None: ...

Multi-level (four-deep)
-----------------------

.. code-block:: python
   :caption: input

   class A:
       def __init__(self, name: str, legs: int, wild: bool = True) -> None: ...

   class B(A):
       def __init__(self, owner: str, **kwargs): super().__init__(**kwargs)

   class C(B):
       def __init__(self, breed: str, **kwargs): super().__init__(**kwargs)

   class D(C):
       def __init__(self, job: str, **kwargs): super().__init__(**kwargs)

.. code-block:: python
   :caption: D.__init__ in generated stub

   class D(C):
       def __init__(
           self,
           job: str,
           breed: str,
           owner: str,
           name: str,
           legs: int,
           wild: bool = True,
       ) -> None: ...

Typed \*args preserved
-----------------------

``*args`` that carry an explicit annotation survive because they represent
a typed variadic — not a blind passthrough:

.. code-block:: python
   :caption: input

   class Container:
       def __init__(self, *elements: "Element", label: str = "", **kwargs):
           super().__init__(**kwargs)

.. code-block:: python
   :caption: generated stub (kwargs resolved from parent)

   class Container(Element):
       def __init__(
           self,
           *elements: Element,
           label: str = '',
           id: Optional[str] = None,
           opacity: float = 1.0,
       ) -> None: ...

\*args and \*\*kwargs together
-------------------------------

When a method has both ``*args`` and ``**kwargs``, both are preserved.
``*args`` always appears before ``**kwargs`` and before any keyword-only
parameters:

.. code-block:: python
   :caption: input

   from typing import Any

   class Case1:
       def __init__(self, x: int, *args: str, flag: bool = False, **kwargs: Any) -> None: ...

.. code-block:: python
   :caption: generated stub

   class Case1:
       def __init__(
           self,
           x: int,
           *args: str,
           flag: bool = False,
           **kwargs: Any,
       ) -> None: ...

\*args in child, \*\*kwargs resolved from parent
-------------------------------------------------

When a child has typed ``*args`` and its ``**kwargs`` resolves from the
parent, ``*args`` is placed after the resolved concrete params:

.. code-block:: python
   :caption: input

   class ParentA:
       def __init__(self, color: str = "black", size: int = 10) -> None: ...

   class ChildA(ParentA):
       def __init__(self, *args: str, **kwargs) -> None:
           super().__init__(**kwargs)

.. code-block:: python
   :caption: generated stub

   class ChildA(ParentA):
       def __init__(
           self,
           color: str = 'black',
           size: int = 10,
           *args: str,
       ) -> None: ...

\*args in child, open \*\*kwargs from parent
---------------------------------------------

When the parent's ``**kwargs`` cannot be fully resolved, ``*args`` is
placed before the residual ``**kwargs``:

.. code-block:: python
   :caption: input

   class ParentB:
       def __init__(self, label: str, **kwargs) -> None: ...

   class ChildB(ParentB):
       def __init__(self, *items: int, **kwargs) -> None:
           super().__init__(**kwargs)

.. code-block:: python
   :caption: generated stub

   class ChildB(ParentB):
       def __init__(
           self,
           label: str,
           *items: int,
           **kwargs,
       ) -> None: ...

Open \*\*kwargs preserved
--------------------------

If the chain cannot be fully resolved (the root ancestor also has
``**kwargs``), the remaining ``**kwargs`` is kept in the stub so the
signature stays correct:

.. code-block:: python
   :caption: input

   class Widget:
       def __init__(self, label: str, **kwargs) -> None: ...

.. code-block:: python
   :caption: generated stub

   class Widget:
       def __init__(self, label: str, **kwargs) -> None: ...

``@classmethod`` with ``cls(**kwargs)``
----------------------------------------

When a classmethod forwards ``**kwargs`` directly into ``cls(...)``,
stubpy detects this via AST analysis and resolves the kwargs against
``cls.__init__`` rather than walking the MRO for the same method name:

.. code-block:: python
   :caption: input

   class Circle(Shape):
       def __init__(self, cx: float, cy: float, r: float, **kwargs): ...

       @classmethod
       def unit(cls, **kwargs) -> "Circle":
           return cls(r=1, cx=0, cy=0, **kwargs)

       @classmethod
       def at_origin(cls, r: float = 50, **kwargs) -> "Circle":
           return cls(r=r, cx=0, cy=0, **kwargs)

.. code-block:: python
   :caption: generated stub

   class Circle(Shape):
       @classmethod
       def unit(
           cls,
           fill: types.Color = 'black',
           opacity: float = 1.0,
           ...
       ) -> Circle: ...

       @classmethod
       def at_origin(
           cls,
           r: float = 50,
           fill: types.Color = 'black',
           opacity: float = 1.0,
           ...
       ) -> Circle: ...

- ``unit``: ``r``, ``cx``, ``cy`` are hardcoded in ``cls(r=1, cx=0, cy=0, ...)`` → **excluded**.
- ``at_origin``: ``r`` is an explicit own parameter → **appears** in the stub. ``cx`` and ``cy`` are hardcoded → excluded.
