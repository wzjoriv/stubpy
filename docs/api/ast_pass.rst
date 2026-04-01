.. _api_ast_pass:

stubpy.ast_pass
===============

.. automodule:: stubpy.ast_pass
   :no-members:

.. autofunction:: stubpy.ast_pass.ast_harvest

.. autoclass:: stubpy.ast_pass.ASTSymbols
   :members:

.. autoclass:: stubpy.ast_pass.ASTHarvester
   :members: harvest

.. rubric:: Data containers

.. autoclass:: stubpy.ast_pass.FunctionInfo
   :members:
.. autoclass:: stubpy.ast_pass.ClassInfo
   :members:
.. autoclass:: stubpy.ast_pass.VariableInfo
   :members:
.. autoclass:: stubpy.ast_pass.TypeVarInfo
   :members:

.. rubric:: Type alias detection

The harvester recognises type alias declarations in four forms:

1. **Explicit annotation** — ``Name: TypeAlias = <rhs>``
2. **PEP 604 bare union** — ``Name = int | float``
3. **Subscripted generic** — ``Name = Union[str, int]``, ``Name = list[int]``
4. **Known type name** — ``Name = int``, ``Name = str``, ``Name = Any``
5. **Python 3.12+ PEP 695** — ``type Name = <rhs>``, ``type Stack[T] = list[T]``

All five forms are stored as :class:`TypeVarInfo` with ``kind="TypeAlias"``
and emitted via :func:`~stubpy.emitter.generate_alias_stub`.

Assignments where the RHS is an arbitrary user-defined name
(``MyAlias = SomeClass``) are **not** promoted — the harvester cannot
determine at parse time whether ``SomeClass`` is a type or a runtime value.
Use ``MyAlias: TypeAlias = SomeClass`` for unambiguous declaration.

.. rubric:: The # stubpy: ignore directive

A source file that begins with ``# stubpy: ignore`` (case-insensitive,
before any code) will have :attr:`~ASTSymbols.skip_file` set to ``True``.
The generator detects this and skips emission, writing only a minimal
stub.  Subsequent comments and blank lines before the first code statement
are also accepted::

    # Auto-generated file — do not stub.
    # stubpy: ignore
    ...
