.. _examples_project_integration:

Integrating stubpy into a project
===================================

This guide shows how to use stubpy end-to-end in a real project, using
the ``demo/`` drawing library included in the repository as the worked
example.

Project layout
--------------

The demo package has this structure:

.. code-block:: text

    demo/
    ├── __init__.py
    ├── types.py       ← shared type aliases (Color, Length, …)
    ├── element.py     ← abstract Element, Style, Transform (NamedTuple)
    ├── container.py   ← Container, Layer, Scene (hierarchy with **kwargs)
    ├── graphics.py    ← Shape, Circle, Rectangle, … (concrete classes)
    ├── functions.py   ← module-level utility functions
    ├── variables.py   ← module-level constants
    └── mixed.py       ← __all__ filtering example

Generating stubs for the whole package
---------------------------------------

.. code-block:: bash

   stubpy demo/ -o stubs/

This produces:

.. code-block:: text

    stubs/
    ├── __init__.pyi
    ├── types.pyi
    ├── element.pyi
    ├── container.pyi
    ├── graphics.pyi
    ├── functions.pyi
    ├── variables.pyi
    └── mixed.pyi

Or from Python:

.. code-block:: python

   from stubpy import generate_package, load_config

   # Pick up any stubpy.toml or [tool.stubpy] in pyproject.toml
   cfg = load_config("demo/")
   result = generate_package("demo/", "stubs/", config=cfg)
   print(result.summary())
   # Generated 8 stubs, 0 failed.

Configuration file
------------------

Add a ``[tool.stubpy]`` section to ``pyproject.toml`` so every developer
gets consistent stubs without having to remember flags:

.. code-block:: toml

    [tool.stubpy]
    output_dir      = "stubs"
    typing_style    = "modern"     # PEP 604  X | None
    execution_mode  = "auto"       # graceful fallback on import errors
    exclude         = ["**/test_*.py", "docs/conf.py"]

Then run with no flags at all:

.. code-block:: bash

   stubpy demo/   # reads pyproject.toml automatically

**kwargs resolution through a class hierarchy
---------------------------------------------

The demo ``container.py`` inherits ``Element.__init__`` through three
levels of ``**kwargs``:

.. code-block:: python

    # element.py
    class Element(ABC):
        def __init__(self, id: str | None = None, title: str | None = None,
                     opacity: float = 1.0, visible: bool = True) -> None: ...

    # container.py
    class Container(Element):
        def __init__(self, *elements: Element,
                     label: str | None = None, **kwargs) -> None: ...

    class Layer(Container):
        def __init__(self, name: str, locked: bool = False, **kwargs) -> None: ...

    class Scene(Container):
        def __init__(self, width: float = 800, height: float = 600,
                     **kwargs) -> None: ...

stubpy resolves the full chain and generates:

.. code-block:: python

    # container.pyi  (generated)
    class Container(Element):
        def __init__(
            self,
            *elements: Element,
            label: str | None = None,
            id: str | None = None,
            title: str | None = None,
            opacity: float = 1.0,
            visible: bool = True,
        ) -> None: ...

    class Layer(Container):
        def __init__(
            self,
            name: str,
            locked: bool = False,
            *,
            label: str | None = None,
            id: str | None = None,
            title: str | None = None,
            opacity: float = 1.0,
            visible: bool = True,
        ) -> None: ...

The bare ``*`` appears because ``Layer`` has no ``*args``, so keyword-only
parameters from ``Container`` and ``Element`` need the separator to be
syntactically valid.

Type alias preservation
-----------------------

The demo ``types.py`` defines named aliases:

.. code-block:: python

    # types.py
    Color     = Union[str, Tuple[float, float, float], Tuple[float, float, float, float]]
    Length    = Union[str, float, int]
    DashArray = Union[str, Sequence[Number]]

These are preserved in ``graphics.py`` stubs instead of being expanded:

.. code-block:: python

    # graphics.pyi  (generated — alias names preserved)
    class Shape(Element):
        def __init__(
            self,
            fill:              types.Color         = 'black',
            stroke_width:      types.Length        = 1,
            stroke_linecap:    types.StrokeLineCap = 'butt',
            stroke:            types.Color | None  = None,
            stroke_dasharray:  types.DashArray | None = None,
            ...
        ) -> None: ...

See :ref:`examples_type_aliases` for full details on alias preservation.

__all__ filtering
-----------------

``mixed.py`` declares ``__all__ = ["DEFAULT_COLOR", "make_scene", "Canvas"]``.
stubpy respects this and only emits those three names:

.. code-block:: python

    # mixed.pyi  (generated)
    DEFAULT_COLOR: str

    def make_scene(width: types.Length = 800, height: types.Length = 600) -> Scene: ...

    class Canvas(Scene):
        def __init__(self, title: str = 'Untitled', ...) -> None: ...

The private ``_private_factory`` and the public-but-unlisted ``helper_func``
are excluded.  Pass ``--include-private`` to override.

Integrating into CI
-------------------

Add a Makefile target or shell script so stubs are always regenerated
when the source changes:

.. code-block:: makefile

    .PHONY: stubs
    stubs:
        stubpy mypackage/ -o stubs/ --strict

The ``--strict`` flag causes a non-zero exit if any ERROR diagnostic
was recorded, failing the CI step.

With ``make``:

.. code-block:: bash

    make stubs

From a ``pre-commit`` hook:

.. code-block:: yaml

    # .pre-commit-config.yaml
    - repo: local
      hooks:
        - id: stubpy
          name: Generate type stubs
          language: system
          entry: stubpy mypackage/ -o stubs/ --strict
          pass_filenames: false
