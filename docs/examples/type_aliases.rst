.. _examples_type_aliases:

Type alias preservation
=======================

When a package uses a dedicated types module (e.g. ``types.py``) to
define named type aliases, stubpy preserves those names in the stub
rather than expanding them to their underlying union.

Setup
-----

Define your type aliases in a sub-module:

.. code-block:: python
   :caption: mypackage/types.py

   from typing import Literal, Sequence, Tuple, Union

   Number         = int | float
   Length         = str | float | int
   Color          = str | Tuple[float, float, float] | Tuple[float, float, float, float]
   StrokeLineCap  = Literal["butt", "round", "square"]
   StrokeLineJoin = Literal["miter", "round", "bevel"]
   DashArray      = Union[str, Sequence[Number]]

Import the sub-module (not individual names) in your source:

.. code-block:: python
   :caption: mypackage/shapes.py

   from mypackage import types        # ← import the module, not `from types import Length`
   from mypackage.element import Element

   class Shape(Element):
       def __init__(
           self,
           fill:             types.Color         = "black",
           stroke_width:     types.Length        = 1,
           stroke_linecap:   types.StrokeLineCap = "butt",
       ) -> None: ...

Generated stub
--------------

.. code-block:: python
   :caption: shapes.pyi (generated)

   from __future__ import annotations
   from typing import Optional
   from mypackage import types
   from mypackage.element import Element

   class Shape(Element):
       def __init__(
           self,
           fill:           types.Color         = 'black',
           stroke_width:   types.Length        = 1,
           stroke_linecap: types.StrokeLineCap = 'butt',
           id:             Optional[str]       = None,
           opacity:        float               = 1.0,
       ) -> None: ...

Compared to the unexpanded alternative:

.. code-block:: python
   :caption: what it would look like without alias preservation

   def __init__(
       self,
       fill:           str | Tuple[float, float, float] | Tuple[float, float, float, float] = 'black',
       stroke_width:   str | float | int = 1,
       stroke_linecap: Literal['butt', 'round', 'square'] = 'butt',
       ...

The alias form is shorter, more readable, and stays in sync with your
types module automatically.

Aliases propagate through ``**kwargs``
--------------------------------------

Type aliases are preserved even when parameters arrive via ``**kwargs``
backtracing.  In the example above, ``id`` and ``opacity`` come from
``Element.__init__`` through ``**kwargs``, but any aliased annotations
among them are still emitted as their alias names.

Only imported modules are scanned
-----------------------------------

stubpy only looks for aliases in sub-modules that are *imported as a
module object* into your source file.  The key is:

.. code-block:: python

   from mypackage import types   # ✓ imports the module — aliases discovered
   from mypackage.types import Length  # ✗ imports a name — aliases NOT discovered

This is intentional: importing individual names gives you full control
over whether stubpy treats them as aliases or expands them.
