.. _examples_project_integration:

Project integration: PixelForge
================================

This example walks through using stubpy on a realistic project — *PixelForge*,
a small SVG/canvas drawing library.  The demo package (``demo/`` in the
repository) is designed so that each module exercises a different set of
stubpy features while remaining a plausible real-world graphics library.

Project layout
--------------

.. code-block:: text

    demo/
    ├── types.py         type aliases (Color, Length, BoundingBox)
    ├── element.py       Element ABC — base for all drawables
    ├── primitives.py    Circle, Rect, Text; dataclass, Enum, TypedDict, ABC
    ├── scene.py         Generic containers (Stack[T], SpatialIndex[K,V]),
    │                    TypeVar, Protocol, TypeAlias, NewType
    ├── style.py         @overload (parse_color, blend, Brush factory),
    │                    GradientStop NamedTuple
    ├── container.py     Container / Layer / Scene — **kwargs backtracing
    │                    through a three-level inheritance chain
    ├── functions.py     Module-level **kwargs forwarding
    │                    (make_color_red → make_color)
    ├── export.py        Cross-file imports, TYPE_CHECKING guard, async export
    ├── graphics.py      Canvas, Renderer — complex class hierarchy
    ├── variables.py     Module-level annotated variables
    └── mixed.py         Mix of all the above

Generating stubs
----------------

.. code-block:: bash

    # Stub the entire package alongside sources:
    stubpy demo/

    # Or write to a separate stubs/ tree:
    stubpy demo/ -o stubs/

    # Or stub multiple modules at once with a glob:
    stubpy "demo/*.py"

Configuration via pyproject.toml
---------------------------------

.. code-block:: toml

    [tool.stubpy]
    include_private = false
    union_style     = "modern"
    output_dir      = "stubs"
    exclude         = ["demo/__pycache__/**"]

    stubpy demo/   # reads pyproject.toml automatically

``**kwargs`` resolution through a class hierarchy
-------------------------------------------------

The demo ``container.py`` inherits ``Element.__init__`` through three
levels of ``**kwargs``:

.. code-block:: python

    # element.py
    class Element:
        def __init__(self, x: float = 0, y: float = 0,
                     label: str | None = None, **kwargs) -> None: ...

    # container.py
    class Container(Element):
        def __init__(self, *elements: Element,
                     clip: bool = False, **kwargs) -> None: ...

    class Layer(Container):
        def __init__(self, name: str, locked: bool = False, **kwargs) -> None: ...

    class Scene(Layer):
        def __init__(self, width: float, height: float, **kwargs) -> None: ...

stubpy walks the MRO and emits the full concrete signature for each class:

.. code-block:: python

    # Generated stub for Scene.__init__
    class Scene(Layer):
        def __init__(
            self,
            width: float,
            height: float,
            name: str = ...,
            locked: bool = False,
            clip: bool = False,
            x: float = 0,
            y: float = 0,
            label: str | None = None,
        ) -> None: ...

Module-level function ``**kwargs`` forwarding
----------------------------------------------

stubpy also expands ``**kwargs`` for standalone functions:

.. code-block:: python

    # functions.py
    def make_color(r: float, g: float, b: float, a: float = 1.0) -> Color: ...
    def make_color_red(r: float = 1.0, **kwargs) -> Color:
        return make_color(r=r, **kwargs)

Generated stub — ``**kwargs`` fully expanded:

.. code-block:: python

    def make_color_red(
        r: float = 1.0,
        *,
        g: float,
        b: float,
        a: float = 1.0,
    ) -> Color: ...

Special class forms
-------------------

``demo/primitives.py`` exercises every major class form in one file:

.. code-block:: python

    # TypedDict
    class RenderOptions(TypedDict, total=False):
        compact: bool
        dpi: float

    # Enum — emits from enum import Enum automatically
    class BlendMode(enum.Enum):
        NORMAL   = "normal"
        MULTIPLY = "multiply"

    # ABC with @abstractmethod + **kwargs MRO backtracing
    class Shape(ABC):
        def __init__(self, *, fill=None, stroke=None,
                     opacity=1.0, blend_mode=BlendMode.NORMAL, **kwargs): ...

    class Circle(Shape):
        def __init__(self, cx, cy, radius, **kwargs): ...

Generated stubs — Enum defaults rendered correctly, kwargs expanded:

.. code-block:: python

    class BlendMode(Enum):
        def __new__(self, value) -> None: ...

    class Circle(Shape):
        def __init__(
            self,
            cx: float,
            cy: float,
            radius: float,
            *,
            fill: Color | None = None,
            stroke: StrokeStyle | None = None,
            opacity: float = 1.0,
            blend_mode: BlendMode = BlendMode.NORMAL,
            visible: bool = True,
        ) -> None: ...
