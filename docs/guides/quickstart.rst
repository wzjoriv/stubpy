.. _quickstart:

Quickstart
==========

Install
-------

.. code-block:: bash

    pip install stubpy
    # or
    uv add stubpy

Requires **Python 3.10+**.

Single file
-----------

.. code-block:: bash

    stubpy path/to/module.py              # writes module.pyi alongside source
    stubpy path/to/module.py -o stubs/   # write to custom directory
    stubpy path/to/module.py --print     # also print to stdout

Multiple files
--------------

Pass several paths in one invocation — stubs are written alongside each source:

.. code-block:: bash

    stubpy a.py b.py c.py
    stubpy "src/*.py"                    # quoted glob (Python-level expansion)
    stubpy module.py mypackage/          # mix files and directories
    stubpy "**/*.py"                     # recursive glob

Whole package
-------------

.. code-block:: bash

    stubpy mypackage/                    # stubs written alongside source files
    stubpy mypackage/ -o stubs/          # custom output directory
    stubpy mypackage/ --union-style legacy   # emit Optional[X] instead of X | None

Configuration file
------------------

Place a ``stubpy.toml`` in the project root (or add ``[tool.stubpy]`` to
``pyproject.toml``):

.. code-block:: toml

    # stubpy.toml
    include_private    = false
    union_style        = "modern"     # "modern" (X | None) | "legacy" (Optional[X])
    alias_style        = "compatible" # "compatible" | "pep695" | "auto"
    include_docstrings = false
    output_dir         = "stubs"
    exclude            = ["**/test_*.py", "docs/conf.py"]

All flags have CLI equivalents; CLI flags override file values.

Python API
----------

.. code-block:: python

    from stubpy import generate_stub, generate_package, StubConfig, StubContext

    # Single file — returns stub content as a string
    content = generate_stub("mymodule.py")
    content = generate_stub("mymodule.py", "stubs/mymodule.pyi")

    # Whole package
    result = generate_package("mypackage/", "stubs/")
    print(result.summary())   # "Generated 12 stubs, 0 failed."

    # Custom config
    cfg = StubConfig(
        include_private    = True,
        union_style        = "legacy",
        include_docstrings = True,
    )
    ctx = StubContext(config=cfg)
    content = generate_stub("mymodule.py", ctx=ctx)

CLI reference
-------------

.. code-block:: text

    usage: stubpy [-h] [-o PATH] [--print] [--include-private]
                  [--include-docstrings] [--verbose] [--strict]
                  [--union-style {modern,legacy}]
                  [--alias-style {compatible,pep695,auto}]
                  [--execution-mode {runtime,ast_only,auto}]
                  [--no-config]
                  path [path ...]

    positional arguments:
      path                  One or more .py files, package directories, or
                            quoted glob patterns (e.g. "src/*.py").

    optional arguments:
      -o PATH               Output .pyi path (file) or root directory (package).
                            Ignored when multiple paths are given.
      --print               Print stub to stdout (single-file mode only).
      --include-private     Include symbols starting with _.
      --include-docstrings  Embed docstrings in stub bodies instead of ...
      --verbose             Print INFO/WARNING/ERROR diagnostics to stderr.
      --strict              Exit 1 if any ERROR diagnostic was recorded.
      --union-style STYLE   modern (X | None, default) or legacy (Optional[X]).
      --alias-style STYLE   compatible (default), pep695, or auto.
      --execution-mode MODE runtime (default), ast_only, or auto.
      --no-config           Ignore stubpy.toml / pyproject.toml.

Type alias style
----------------

Use ``--alias-style`` to control how type alias declarations are emitted:

.. code-block:: bash

    stubpy mymodule.py --alias-style compatible   # Name: TypeAlias = rhs  (3.10+)
    stubpy mymodule.py --alias-style pep695       # type Name = rhs        (3.12+)
    stubpy mymodule.py --alias-style auto         # selects based on runtime Python

Extending the annotation dispatcher
------------------------------------

Use :func:`~stubpy.annotations.register_annotation_handler` to teach stubpy
how to render custom annotation types:

.. code-block:: python

    from stubpy.annotations import register_annotation_handler, annotation_to_str
    from mylib import Validated

    @register_annotation_handler(lambda a: isinstance(a, Validated))
    def _handle_validated(annotation, ctx):
        inner = annotation_to_str(annotation.inner_type, ctx)
        return f"Validated[{inner}]"

Handlers registered this way are appended *after* all built-in handlers and
are called for any annotation that no built-in handler matches.
