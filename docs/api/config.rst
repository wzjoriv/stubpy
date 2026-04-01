.. _api_config:

stubpy.config
=============

.. automodule:: stubpy.config
   :no-members:

.. autofunction:: stubpy.config.find_config_file
.. autofunction:: stubpy.config.load_config

.. rubric:: Configuration file format

stubpy reads configuration from the first file found by walking upward
from the target directory:

1. ``stubpy.toml`` — the whole file is the config section.
2. ``pyproject.toml`` — only the ``[tool.stubpy]`` section is read.

**stubpy.toml example:**

.. code-block:: toml

    include_private = false
    execution_mode  = "runtime"    # "runtime" | "ast_only" | "auto"
    typing_style    = "modern"     # "modern" (X | None) | "legacy" (Optional[X])
    output_dir      = "stubs"
    exclude         = ["**/test_*.py", "setup.py"]

**pyproject.toml example:**

.. code-block:: toml

    [tool.stubpy]
    include_private = false
    typing_style    = "legacy"
    exclude         = ["docs/conf.py"]

.. rubric:: TOML parsing

On Python 3.11+ the stdlib :mod:`tomllib` is used.  On Python 3.10 the
``tomli`` backport is used if installed; otherwise a minimal built-in
parser handles the simple key/value syntax that stubpy needs.  Unknown
keys are silently ignored so that future versions can add new options
without breaking existing config files.

.. rubric:: Supported keys

.. list-table::
   :widths: 22 12 66
   :header-rows: 1

   * - Key
     - Default
     - Description
   * - ``include_private``
     - ``false``
     - Include symbols whose names start with ``_``.
   * - ``respect_all``
     - ``true``
     - When ``__all__`` is present, only stub names listed in it.
   * - ``execution_mode``
     - ``"runtime"``
     - ``"runtime"`` / ``"ast_only"`` / ``"auto"``.
   * - ``typing_style``
     - ``"modern"``
     - ``"modern"`` emits ``X | None``; ``"legacy"`` emits ``Optional[X]``.
   * - ``output_dir``
     - ``null``
     - Output root for :func:`~stubpy.generator.generate_package`.
   * - ``exclude``
     - ``[]``
     - Glob patterns (relative) for files to skip in package processing.
   * - ``verbose``
     - ``false``
     - Print all diagnostics to ``stderr``.
   * - ``strict``
     - ``false``
     - Exit with code 1 if any ERROR diagnostic is recorded.
