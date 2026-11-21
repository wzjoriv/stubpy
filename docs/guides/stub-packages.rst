Stub-only packages
==================

A stub-only package ships a library's stubs on their own, the way typeshed publishes
``types-*`` packages (:pep:`561`). Use it when you stub a library you do not maintain, or
want the stubs released separately from the code.

.. code-block:: console

   $ stubpy src/mypkg -o dist-stubs --stub-package
   $ cd dist-stubs/mypkg-stubs && pip wheel --no-deps .

``--stub-package`` (config key ``stub_package``) needs an output folder. Each top-level
package becomes a distribution folder:

.. code-block:: text

   dist-stubs/
       mypkg-stubs/
           pyproject.toml
           mypkg-stubs/
               __init__.pyi
               py.typed          # "partial"
               core.pyi

A top-level module ``mod.py`` becomes ``mod-stubs/mod-stubs/__init__.pyi``.

``pyproject.toml`` names the distribution ``mypkg-stubs``, takes its version from the
installed ``mypkg`` (``0`` when it is not installed), sets ``requires-python`` from
``target_python`` and builds with setuptools. ``py.typed`` says ``partial``, so a type
checker still reads the package's own inline types for modules the stubs leave out.

stubpy rewrites both files on every run. ``stubpy check --stub-package`` reports them as
stale when they are missing or differ, as it does for stubs.
