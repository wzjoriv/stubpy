.. _how_it_works:

How it works
============

stubpy is a pipeline of nine focused stages.  Each stage is a separate
module with a single responsibility, and all mutable run-state is held in
a :class:`~stubpy.context.StubContext` that is created fresh for every
call to :func:`~stubpy.generator.generate_stub`.

.. code-block:: text

   generate_stub(filepath)
       │
       ├─ 1. loader      load_module()              → module, path, name
       ├─ 2. ast_pass    ast_harvest()              → ASTSymbols
       ├─ 3. imports     scan_import_statements()   → import_map
       ├─ 4. aliases     build_alias_registry()     → ctx populated
       ├─ 5. symbols     build_symbol_table()       → SymbolTable
       ├─ 6. generator   collect_classes()          → sorted class list
       │       └─ for each class:
       │           emitter  generate_class_stub()
       │               └─ for each method:
       │                   resolver  resolve_params()
       │                   emitter   generate_method_stub()  ← uses raw AST anns
       └─ 7. generator   assemble header + body     → write .pyi

Stage 1 - Module loading
------------------------

:mod:`stubpy.loader` uses :func:`importlib.util.spec_from_file_location`
to load the source file as a live Python module.  The file's parent
directory *and* its grandparent are temporarily added to :data:`sys.path`
so that package-relative imports inside the target file resolve correctly,
then removed once loading completes.

Any load error is recorded in ``ctx.diagnostics`` at the
:attr:`~stubpy.diagnostics.DiagnosticStage.LOAD` stage before being
re-raised.

Stage 2 - AST pre-pass
----------------------

:func:`~stubpy.ast_pass.ast_harvest` performs a **read-only** pass over
the source AST *before* any code is executed.  No import side-effects,
no ``exec``, no ``importlib`` — just ``ast.parse`` and ``ast.unparse``.

The harvester collects into an :class:`~stubpy.ast_pass.ASTSymbols`
container:

- All top-level **class** definitions with their base-class expressions
  and decorator names.
- All top-level **function** definitions (sync and ``async``) with their
  decorator names, raw argument annotation strings, and raw return
  annotation string.  ``@overload``-decorated variants are flagged.
- All top-level **annotated** variables (``name: Type = value``) and
  plain assignments.
- The ``__all__`` declaration, when present.
- ``TypeVar``, ``TypeAlias``, ``ParamSpec``, ``TypeVarTuple``, and
  ``NewType`` declarations.

Why does this matter?  Python's ``typing.Union`` *flattens* nested unions
at evaluation time.  If a developer writes ``Union[types.Color, int]``
where ``Color = Union[str, Tuple[...]]``, the runtime annotation is
``Union[str, Tuple[...], int]`` — the ``Color`` alias boundary is gone.
The AST pre-pass captures the original string ``"Union[types.Color, int]"``
before evaluation, enabling the emitter to preserve the alias in the stub.

Stage 3 - Import scanning
-------------------------

:mod:`stubpy.imports` parses the source AST to build a
``{local_name: import_statement}`` map of every import in the file.  This
map is used later to:

- discover type-alias sub-modules (Stage 4),
- re-emit cross-file class imports in the ``.pyi`` header (Stage 7 — Header assembly).

Stage 4 - Alias registry
------------------------

:mod:`stubpy.aliases` scans the loaded module for imported sub-modules
(e.g. ``from demo import types``).  Any attribute of such a sub-module
that is a type alias — a PEP 604 union (``str | int``) or a subscripted
typing generic (``List[str]``, ``Literal["a"]``) — is registered in the
:class:`~stubpy.context.StubContext`.

When :func:`~stubpy.annotations.annotation_to_str` encounters a matching
annotation later, it emits ``types.Length`` instead of expanding it to
``str | float | int``.  This also handles ``Optional[types.Color]``,
``tuple[types.Color, types.Length]``, and similar container forms.

Stage 5 - Symbol table
----------------------

:func:`~stubpy.symbols.build_symbol_table` merges the live module objects
from Stage 1 with the AST metadata from Stage 2 into a unified
:class:`~stubpy.symbols.SymbolTable`.

Each entry is a typed :class:`~stubpy.symbols.StubSymbol` subclass:

- :class:`~stubpy.symbols.ClassSymbol` — live ``type`` object +
  :class:`~stubpy.ast_pass.ClassInfo` (bases, decorators, methods with
  raw annotations).
- :class:`~stubpy.symbols.FunctionSymbol` — callable + is_async flag.
- :class:`~stubpy.symbols.VariableSymbol` — live value + annotated or
  inferred type string.
- :class:`~stubpy.symbols.AliasSymbol` — ``TypeAlias`` / ``NewType``
  declaration.
- :class:`~stubpy.symbols.OverloadGroup` — multiple ``@overload``
  variants sharing one name.

If ``__all__`` was found in Stage 2, it is stored as a ``set[str]`` in
``ctx.all_exports`` and used to filter the symbol table to public names
only.

Stage 6 - Collect, resolve, and emit
------------------------------------

:mod:`stubpy.resolver` implements the core ``**kwargs`` / ``*args``
backtracing logic via :func:`~stubpy.resolver.resolve_params`.  Three
strategies are tried in order:

1. **No variadics** — return the method's own parameters unchanged.

2. **@classmethod cls() detection** — if the method is a ``@classmethod``
   and its AST contains a call ``cls(..., **kwargs)``, the ``**kwargs`` is
   resolved against ``cls.__init__`` (which is itself fully resolved).
   Parameters explicitly passed in the ``cls(...)`` call are excluded from
   the stub.

3. **MRO walk** — iterate the class MRO, collecting concrete parameters
   from each ancestor that defines the same method, until no unresolved
   ``**kwargs`` or ``*args`` remain.

   Typed ``*args`` (e.g. ``*elements: Element``) always survive because
   they carry explicit annotation information that should not be discarded.

Stage 6a - Annotation conversion
--------------------------------

:mod:`stubpy.annotations` converts live annotation objects to stub-safe
strings using a *dispatch table* rather than an if/elif chain.  Each
annotation kind is handled by a small function decorated with
``@_register(predicate)``.

Resolution order inside :func:`~stubpy.annotations.annotation_to_str`:

1. ``inspect.Parameter.empty`` → ``""``
2. Alias-registry lookup → e.g. ``"types.Length"``
3. Registered dispatch handlers, in registration order
4. Fallback: ``str(annotation).replace("typing.", "")``

Handled forms include: plain types, ``NoneType``, ``...`` (Ellipsis),
string forward references, ``typing.ForwardRef``, PEP 604 ``X | Y``
unions, ``typing.Union``, ``Optional``, ``Callable``, ``Literal``,
``tuple`` / ``Tuple``, ``list`` / ``List``, ``dict`` / ``Dict``, and
all other subscripted generics.

For multi-type aliases used in ``Optional`` / ``| None`` positions, the
handler rebuilds the non-``None`` sub-union and checks the alias registry
on it before expanding each constituent type individually.

Stage 6b - Emission
-------------------

:mod:`stubpy.emitter` formats each class and method into ``.pyi`` text.
Methods with ≤ 2 non-self parameters stay on one line; longer signatures
are split across lines with a trailing comma on each parameter for clean
diffs.

When the :class:`~stubpy.symbols.SymbolTable` has AST info for a method,
:func:`~stubpy.annotations.format_param` is called with a
``raw_ann_override`` — the original annotation string from the source.
When that string references a registered alias module prefix (e.g.
``"types."``), it takes priority over the runtime-evaluated annotation,
recovering alias names that Python's union-flattening would otherwise
destroy.

Stage 7 - Header assembly and write
-----------------------------------

:mod:`stubpy.generator` assembles the file header:

- ``from __future__ import annotations``
- ``from typing import ...`` (only the names actually used in the body)
- Type-module imports for aliases that were referenced
- Cross-file class imports for base classes / annotation types

The complete content is written to disk and returned as a string.

Diagnostic collection
---------------------

Every stage that can fail logs to ``ctx.diagnostics`` — a
:class:`~stubpy.diagnostics.DiagnosticCollector` — rather than silently
swallowing exceptions.  Each :class:`~stubpy.diagnostics.Diagnostic`
records a :class:`~stubpy.diagnostics.DiagnosticLevel` (``INFO``,
``WARNING``, ``ERROR``), a :class:`~stubpy.diagnostics.DiagnosticStage`,
the symbol name being processed, and a human-readable message.

The ``--verbose`` CLI flag prints all diagnostics to ``stderr``.
The ``--strict`` flag causes a non-zero exit if any ``ERROR`` was recorded.
