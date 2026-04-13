.. _examples_extending:

Extending and embedding stubpy
================================

This page shows how to go beyond the defaults: custom annotation rendering,
docstring-embedded stubs, CI integration, and using the Python API directly.

Custom annotation handlers
--------------------------

Use :func:`~stubpy.annotations.register_annotation_handler` to teach stubpy
how to render annotation types it doesn't recognise out of the box.  This is
useful for Pydantic, attrs, beartype, and any other library that uses custom
annotation objects at runtime.

.. code-block:: python

    from stubpy.annotations import register_annotation_handler, annotation_to_str

    # Suppose your library has an Annotated-like wrapper:
    class Validated:
        def __init__(self, inner):
            self.inner = inner

    @register_annotation_handler(lambda a: isinstance(a, Validated))
    def _handle_validated(annotation, ctx):
        inner_str = annotation_to_str(annotation.inner, ctx)
        return f"Validated[{inner_str}]"

    # Now stubs for functions annotated with Validated(int) emit Validated[int]

To run *before* built-in handlers, insert directly into the table:

.. code-block:: python

    from stubpy.annotations import _ANN_HANDLERS
    _ANN_HANDLERS.insert(0, (my_predicate, my_handler))

Including docstrings in stubs
------------------------------

Use ``--include-docstrings`` (or ``include_docstrings = true`` in config) to
embed each symbol's docstring as a triple-quoted body.  This is useful when
the ``.pyi`` file serves as quick-reference documentation in your IDE:

.. code-block:: bash

    stubpy mymodule.py --include-docstrings

.. code-block:: python

    # Without --include-docstrings (default)
    def area(self, *, unit: str = "px") -> float: ...

    # With --include-docstrings
    def area(self, *, unit: str = "px") -> float:
        """Return the area in *unit* units."""

.. code-block:: toml

    # stubpy.toml
    include_docstrings = true

Using the Python API
---------------------

stubpy's Python API gives you full control:

.. code-block:: python

    from stubpy import generate_stub, generate_package, StubConfig, StubContext

    # Fine-grained context per file
    cfg = StubConfig(
        include_private    = True,
        union_style        = "legacy",    # Optional[X] instead of X | None
        include_docstrings = True,
    )
    ctx = StubContext(config=cfg)
    stub_text = generate_stub("mymodule.py", ctx=ctx)

    # Inspect diagnostics after the run
    for d in ctx.diagnostics:
        if d.level.name == "WARNING":
            print(f"  {d.symbol}: {d.message}")

    # Package with custom context factory (one ctx per file)
    result = generate_package(
        "mypackage/",
        output_dir="stubs/",
        ctx_factory=lambda: StubContext(config=cfg),
    )
    print(result.summary())
    for path, diags in result.failed:
        print(f"  FAILED: {path}")

CI / pre-commit integration
----------------------------

**GitHub Actions:**

.. code-block:: yaml

    - name: Generate stubs
      run: |
        pip install stubpy
        stubpy src/ -o stubs/
        git diff --exit-code stubs/   # fail if stubs are out of date

**pre-commit hook** (add to ``.pre-commit-config.yaml``):

.. code-block:: yaml

    repos:
      - repo: local
        hooks:
          - id: stubpy
            name: Generate type stubs
            entry: stubpy
            args: [src/, -o, stubs/]
            language: python
            types: [python]
            pass_filenames: false

**Makefile target:**

.. code-block:: makefile

    stubs:
        stubpy src/ -o stubs/

    check-stubs: stubs
        git diff --exit-code stubs/

Execution modes
---------------

Three modes control whether the source module is actually imported:

.. code-block:: bash

    # RUNTIME (default): import + full introspection
    stubpy module.py

    # AST_ONLY: parse only — safe for modules with side effects at import time
    stubpy module.py --execution-mode ast_only

    # AUTO: try runtime, fall back to AST-only on ImportError
    stubpy module.py --execution-mode auto

.. code-block:: python

    from stubpy import generate_stub
    from stubpy.context import ExecutionMode, StubConfig, StubContext

    ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AUTO))
    stub = generate_stub("heavy_module.py", ctx=ctx)

``# stubpy: ignore``
----------------------

Place ``# stubpy: ignore`` at the top of any ``.py`` file to skip it
entirely during stub generation (useful for generated code, C extensions,
or test helpers):

.. code-block:: python

    # stubpy: ignore
    # This file is auto-generated — do not stub.

    ...

stubpy writes a minimal ``from __future__ import annotations`` stub and
records an ``INFO`` diagnostic.
