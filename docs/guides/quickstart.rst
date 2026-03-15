.. _quickstart:

Quickstart
==========

CLI
---

The simplest usage is to point stubpy at a ``.py`` file.  The stub is
written next to the source by default:

.. code-block:: bash

   stubpy path/to/mymodule.py
   # → writes path/to/mymodule.pyi

To specify a custom output path:

.. code-block:: bash

   stubpy path/to/mymodule.py -o stubs/mymodule.pyi

To also print the generated stub to stdout:

.. code-block:: bash

   stubpy path/to/mymodule.py --print

Full CLI reference:

.. code-block:: text

   usage: stubpy [-h] [-o PATH] [--print] file

   positional arguments:
     file          Python source file to stub

   optional arguments:
     -h, --help    show this help message and exit
     -o PATH       Output .pyi path (default: same stem and directory as input)
     --print       Print the generated stub to stdout after writing

Python API
----------

.. code-block:: python

   from stubpy import generate_stub

   # Write stub alongside the source, return content as a string
   content = generate_stub("path/to/mymodule.py")

   # Write to a custom path
   content = generate_stub("path/to/mymodule.py", "out/mymodule.pyi")

A complete example
------------------

Given this source file ``shapes.py``:

.. code-block:: python

   from typing import Optional

   class Shape:
       def __init__(
           self,
           color: str = "black",
           opacity: float = 1.0,
       ) -> None:
           self.color   = color
           self.opacity = opacity

   class Circle(Shape):
       def __init__(self, radius: float, **kwargs) -> None:
           super().__init__(**kwargs)
           self.radius = radius

       @classmethod
       def unit(cls, **kwargs) -> "Circle":
           return cls(radius=1.0, **kwargs)

Running:

.. code-block:: bash

   stubpy shapes.py --print

Produces:

.. code-block:: python

   from __future__ import annotations
   from typing import Optional

   class Shape:
       def __init__(
           self,
           color: str = 'black',
           opacity: float = 1.0,
       ) -> None: ...

   class Circle(Shape):
       def __init__(
           self,
           radius: float,
           color: str = 'black',
           opacity: float = 1.0,
       ) -> None: ...
       @classmethod
       def unit(
           cls,
           color: str = 'black',
           opacity: float = 1.0,
       ) -> Circle: ...

Notice that:

- ``**kwargs`` in ``Circle.__init__`` is **resolved** to ``color`` and
  ``opacity`` from ``Shape.__init__``.
- ``Circle.unit`` is a ``@classmethod`` that calls ``cls(radius=1.0, **kwargs)``;
  because ``radius`` is hardcoded, it is excluded from the stub, and only the
  remaining ``Shape`` params appear.
