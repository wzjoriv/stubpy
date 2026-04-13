.. _examples_mro_backtracing:

MRO backtracing
================

stubpy's defining feature is **MRO backtracing** — walking a class's
Method Resolution Order to expand ``**kwargs`` into the concrete named
parameters they actually represent.  This page explains how it works and
what the generated stubs look like.

The problem
-----------

Python inheritance commonly uses ``**kwargs`` to forward keyword arguments
up the chain without listing every parameter in every subclass:

.. code-block:: python

    class Widget:
        def __init__(self, color: str = "black", size: int = 12) -> None: ...

    class Button(Widget):
        def __init__(self, label: str, **kwargs) -> None:
            super().__init__(**kwargs)

Without MRO backtracing, a stub generator would emit:

.. code-block:: python

    class Button(Widget):
        def __init__(self, label: str, **kwargs) -> None: ...  # IDE sees no kwargs

With ``**kwargs`` opaque, IDEs cannot autocomplete ``color`` or ``size``
on ``Button()``, and type checkers cannot catch typos like
``Button("OK", colour="red")``.

What stubpy does
----------------

stubpy imports the module, inspects the live class hierarchy, and walks the
MRO to find where every ``**kwargs`` terminates:

.. code-block:: python

    # Generated stub — full concrete signature
    class Button(Widget):
        def __init__(
            self,
            label: str,
            color: str = 'black',
            size: int = 12,
        ) -> None: ...

The IDE now auto-completes ``color`` and ``size`` on ``Button()`` and type
checkers catch ``Button("OK", colour="red")`` as an error.

Three-level inheritance
-----------------------

MRO backtracing works across arbitrarily deep hierarchies:

.. code-block:: python

    class Element:
        def __init__(self, x: float = 0.0, y: float = 0.0,
                     visible: bool = True) -> None: ...

    class Container(Element):
        def __init__(self, clip: bool = False, **kwargs) -> None:
            super().__init__(**kwargs)

    class Scene(Container):
        def __init__(self, width: float, height: float, **kwargs) -> None:
            super().__init__(**kwargs)

Generated stubs:

.. code-block:: python

    class Container(Element):
        def __init__(
            self,
            clip: bool = False,
            x: float = 0.0,
            y: float = 0.0,
            visible: bool = True,
        ) -> None: ...

    class Scene(Container):
        def __init__(
            self,
            width: float,
            height: float,
            clip: bool = False,
            x: float = 0.0,
            y: float = 0.0,
            visible: bool = True,
        ) -> None: ...

``@classmethod`` with ``cls(...)`` pattern
------------------------------------------

When a ``@classmethod`` forwards ``**kwargs`` into ``cls(...)``, stubpy
detects that pattern via AST analysis and resolves the kwargs against
``cls.__init__`` rather than the MRO siblings:

.. code-block:: python

    class Circle(Element):
        def __init__(self, radius: float, **kwargs) -> None:
            super().__init__(**kwargs)

        @classmethod
        def unit(cls, **kwargs) -> "Circle":
            return cls(radius=1.0, **kwargs)

Generated stub:

.. code-block:: python

    class Circle(Element):
        def __init__(
            self,
            radius: float,
            x: float = 0.0,
            y: float = 0.0,
            visible: bool = True,
        ) -> None: ...

        @classmethod
        def unit(
            cls,
            x: float = 0.0,
            y: float = 0.0,
            visible: bool = True,
        ) -> Circle: ...

Module-level function forwarding
---------------------------------

stubpy also expands ``**kwargs`` for standalone functions.  The AST body is
scanned to detect which callable receives the forwarded kwargs:

.. code-block:: python

    def make_color(r: float, g: float, b: float, a: float = 1.0) -> Color: ...

    def make_red(r: float = 1.0, **kwargs) -> Color:
        return make_color(r=r, **kwargs)

Generated stub:

.. code-block:: python

    def make_red(
        r: float = 1.0,
        *,
        g: float,
        b: float,
        a: float = 1.0,
    ) -> Color: ...

Positional-only parameters (``/``)
-----------------------------------

When a parent method has positional-only parameters and a child absorbs them
via ``**kwargs``, stubpy promotes them to ``POSITIONAL_OR_KEYWORD`` — callers
pass them by keyword through the child's interface, so emitting them as
positional-only would produce an invalid ``/`` placement:

.. code-block:: python

    class Renderer:
        def draw(self, x: float, y: float, /, *, antialias: bool = True): ...

    class Canvas(Renderer):
        def draw(self, **kwargs): ...   # absorbs x, y via **kwargs

Generated stub:

.. code-block:: python

    class Canvas(Renderer):
        # x and y promoted from POSITIONAL_ONLY to POSITIONAL_OR_KEYWORD
        def draw(self, x: float, y: float, *, antialias: bool = True): ...

Default-ordering enforcement
-----------------------------

When absorbed parameters (which have no default) would follow a parameter
that has a default, stubpy automatically promotes the absorbed parameters to
keyword-only — they are semantically keyword arguments anyway, since they
arrived via ``**kwargs``:

.. code-block:: python

    def make_color(r: float, g: float, b: float, a: float = 1.0) -> Color: ...
    def make_red(r: float = 1.0, **kwargs) -> Color: ...

    # Without promotion: make_red(r=1.0, g, b, a=1.0) — INVALID (non-default after default)
    # With promotion:
    def make_red(r: float = 1.0, *, g: float, b: float, a: float = 1.0) -> Color: ...
