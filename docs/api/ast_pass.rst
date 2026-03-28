.. _api_ast_pass:

stubpy.ast_pass
===============

.. automodule:: stubpy.ast_pass
   :no-members:

.. autofunction:: stubpy.ast_pass.ast_harvest

.. autoclass:: stubpy.ast_pass.ASTSymbols
   :no-index:
   :members:
   :exclude-members: classes, functions, variables, typevar_decls, all_exports

   .. rubric:: Fields

   .. attribute:: classes
      :type: list[ClassInfo]

      All top-level class definitions, in source order.

   .. attribute:: functions
      :type: list[FunctionInfo]

      All top-level function definitions, in source order.

   .. attribute:: variables
      :type: list[VariableInfo]

      All top-level annotated and plain variable assignments.

   .. attribute:: typevar_decls
      :type: list[TypeVarInfo]

      ``TypeVar``, ``ParamSpec``, ``TypeVarTuple``, ``TypeAlias``, and
      ``NewType`` declarations.

   .. attribute:: all_exports
      :type: list[str] or None

      Contents of ``__all__``, or ``None`` when the module has no
      ``__all__`` declaration.

.. autoclass:: stubpy.ast_pass.ClassInfo
   :members:

.. autoclass:: stubpy.ast_pass.FunctionInfo
   :members:

.. autoclass:: stubpy.ast_pass.VariableInfo
   :members:

.. autoclass:: stubpy.ast_pass.TypeVarInfo
   :members:

.. rubric:: Notes

:func:`ast_harvest` is a thin wrapper around
:class:`ASTHarvester` — a :class:`ast.NodeVisitor` subclass that
visits only the **top-level** body of the module.  Definitions nested
inside ``if TYPE_CHECKING:`` blocks are also harvested because the
visitor recurses transitively into ``if`` / ``else`` / ``with`` /
``try`` bodies.

The key motivation for this stage is to preserve annotation strings
**before** Python's ``typing.Union`` flattening can destroy alias
boundaries.  See :ref:`how_it_works` for details.
