Extending stubpy
================

:mod:`stubpy.extend` is the advanced namespace: annotation handlers, the run context, the
symbol table, harvesting and diagnostics. Its API is less settled than the one in
:doc:`../reference/api`.

Custom annotation handlers
--------------------------

When an annotation is an object stubpy does not recognise, it is written as ``<... object at
0x...>``. A handler turns it into stub text.

.. code-block:: python

   # vlib.py
   class Validated:
       def __init__(self, inner_type):
           self.inner_type = inner_type

   # service.py
   from vlib import Validated

   def clamp(value: Validated(int), lo: Validated(float) = 0.0) -> int: ...

Without a handler, ``stubpy render service.py`` writes:

.. code-block:: python

   def clamp(value: <vlib.Validated object at 0x000001D36F530690>, lo: <vlib.Validated object at 0x000001D36F530550> = 0.0) -> int: ...

Register one, then render from Python:

.. code-block:: python

   import stubpy
   from stubpy.extend import annotation_to_str, register_annotation_handler

   from vlib import Validated


   @register_annotation_handler(lambda a: isinstance(a, Validated))
   def _validated(annotation, ctx):
       return f"Validated[{annotation_to_str(annotation.inner_type, ctx)}]"


   print(stubpy.render("service.py").text)

.. code-block:: python

   from __future__ import annotations
   from vlib import Validated

   def clamp(value: Validated[int], lo: Validated[float] = 0.0) -> int: ...

Rules:

* ``predicate(annotation) -> bool`` selects the annotations; ``handler(annotation, ctx) -> str``
  returns the text.
* A handler runs after the built-in ones and only sees what they did not match.
  ``first=True`` puts it ahead of all of them.
* Call ``annotation_to_str(inner, ctx)`` to render nested types, so aliases and imports are
  tracked in ``ctx``.
* The predicate must match the class object stubpy sees. The module you stub is imported
  by stubpy, so import the annotation class from an importable library module, as above.
  The handler list is global to the process.

.. note::

   Handlers only apply to live annotation objects, so they take effect in ``runtime`` mode.

Symbol table access
-------------------

``ast_harvest`` reads a source string and ``build_symbol_table`` turns it into a
:class:`~stubpy.extend.SymbolTable`. Pass ``None`` as the live module to work from source
alone.

.. code-block:: python

   from stubpy.extend import ast_harvest, build_symbol_table

   source = open("mro.py").read()
   table = build_symbol_table(None, "mro", ast_harvest(source))
   print(table.all_names())            # ['Element', 'Styled', 'Circle']
   styled = table.get_class("Styled")
   print(styled.ast_info.bases)        # ['Element']

The table offers ``get``, ``get_class``, ``get_function``, ``classes()``, ``functions()``,
``variables()``, ``aliases()``, ``overload_groups()``, ``by_kind(kind)`` and ``sorted_by_line()``.
Its symbols are :class:`~stubpy.extend.ClassSymbol`, :class:`~stubpy.extend.FunctionSymbol`,
:class:`~stubpy.extend.VariableSymbol`, :class:`~stubpy.extend.AliasSymbol` and
:class:`~stubpy.extend.OverloadGroup`.

Diagnostics and context
-----------------------

:class:`~stubpy.extend.StubContext` carries the :class:`~stubpy.Config`, the diagnostics
collector and the import bookkeeping for one module. Handlers receive it as ``ctx``.
Record issues instead of raising:

.. code-block:: python

   from stubpy.extend import Stage

   ctx.diagnostics.warning(Stage.EMIT, "Validated", "no inner type")

Every public name of the namespace is listed in :doc:`../reference/extend`.
