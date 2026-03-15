.. _examples_cross_file:

Cross-file class references
============================

When a module imports classes from other local modules and uses them as
base classes or in type annotations, stubpy automatically re-emits the
necessary import statements in the generated ``.pyi`` header.

Example setup
-------------

.. code-block:: python
   :caption: shapes/element.py

   from typing import Optional

   class Element:
       def __init__(self, id: Optional[str] = None, opacity: float = 1.0) -> None:
           ...

.. code-block:: python
   :caption: shapes/container.py

   from shapes.element import Element
   from typing import Iterator, List, Optional

   class Container(Element):
       def __init__(
           self,
           *elements: Element,
           label: Optional[str] = None,
           **kwargs,
       ) -> None:
           super().__init__(**kwargs)

       def add(self, *elements: Element) -> "Container": ...
       def get(self, index: int) -> Element: ...
       def __iter__(self) -> Iterator[Element]: ...

Generated stub
--------------

.. code-block:: python
   :caption: container.pyi (generated)

   from __future__ import annotations
   from typing import Iterator, Optional
   from shapes.element import Element       # ← re-emitted automatically

   class Container(Element):
       def __init__(
           self,
           *elements: Element,
           label: Optional[str] = None,
           id: Optional[str] = None,
           opacity: float = 1.0,
       ) -> None: ...
       def add(self, *elements: Element) -> Container: ...
       def get(self, index: int) -> Element: ...
       def __iter__(self) -> Iterator[Element]: ...

stubpy detects ``Element`` in:

- the base class list ``class Container(Element)``
- parameter annotations ``*elements: Element``, ``-> Element``

and resolves the import statement for ``Element`` from the source file's
own imports.

Three-level chain
-----------------

Cross-file resolution is not limited to one level.  A ``Layer`` that
extends ``Container`` (in a third file) produces a stub with the full
three-level chain resolved:

.. code-block:: python
   :caption: shapes/layers.py

   from shapes.container import Container

   class Layer(Container):
       def __init__(self, name: str, locked: bool = False, **kwargs) -> None:
           super().__init__(**kwargs)

.. code-block:: python
   :caption: layers.pyi (generated)

   from __future__ import annotations
   from typing import Optional
   from shapes.container import Container

   class Layer(Container):
       def __init__(
           self,
           name: str,
           locked: bool = False,
           *,
           label: Optional[str] = None,
           id: Optional[str] = None,
           opacity: float = 1.0,
       ) -> None: ...

Notice the bare ``*`` separator: ``Layer`` has no ``*args``, so the
keyword-only parameters (``label``, ``id``, ``opacity``) require an
explicit ``*`` in the stub to remain syntactically valid.

What is not re-emitted
----------------------

stubpy does not re-emit:

- ``from typing import ...`` — these are collected separately and merged into a single import line.
- ``from __future__ import annotations`` — always emitted as the first line.
- Names that are defined in the *same* module being stubbed.
