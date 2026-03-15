.. _examples_basic:

Basic stub generation
=====================

Plain class with annotations
-----------------------------

.. code-block:: python
   :caption: shapes.py

   class Rectangle:
       def __init__(self, width: float, height: float) -> None:
           self.width  = width
           self.height = height

       def area(self) -> float:
           return self.width * self.height

       def perimeter(self) -> float:
           return 2 * (self.width + self.height)

.. code-block:: bash

   stubpy shapes.py --print

.. code-block:: python
   :caption: shapes.pyi (generated)

   from __future__ import annotations

   class Rectangle:
       def __init__(self, width: float, height: float) -> None: ...
       def area(self) -> float: ...
       def perimeter(self) -> float: ...

Default values
--------------

Default parameter values are preserved exactly as ``repr()`` would render
them:

.. code-block:: python
   :caption: input

   class Config:
       def __init__(
           self,
           host: str = "localhost",
           port: int = 8080,
           debug: bool = False,
       ) -> None: ...

.. code-block:: python
   :caption: generated stub

   class Config:
       def __init__(
           self,
           host: str = 'localhost',
           port: int = 8080,
           debug: bool = False,
       ) -> None: ...

Properties and setters
-----------------------

.. code-block:: python
   :caption: input

   class Temperature:
       @property
       def celsius(self) -> float:
           return self._c

       @celsius.setter
       def celsius(self, value: float) -> None:
           self._c = value

.. code-block:: python
   :caption: generated stub

   class Temperature:
       @property
       def celsius(self) -> float: ...
       @celsius.setter
       def celsius(self, value: float) -> None: ...

Classmethods and staticmethods
--------------------------------

.. code-block:: python
   :caption: input

   class Vector:
       def __init__(self, x: float, y: float) -> None: ...

       @classmethod
       def origin(cls) -> "Vector":
           return cls(0.0, 0.0)

       @staticmethod
       def dot(a: "Vector", b: "Vector") -> float:
           return a.x * b.x + a.y * b.y

.. code-block:: python
   :caption: generated stub

   class Vector:
       def __init__(self, x: float, y: float) -> None: ...
       @classmethod
       def origin(cls) -> Vector: ...
       @staticmethod
       def dot(a: Vector, b: Vector) -> float: ...
