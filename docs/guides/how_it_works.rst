.. _how_it_works:

How it works
============

stubpy is a pipeline of eight focused stages.  Each stage is a separate
module with a single responsibility, and all mutable run-state is held in
a :class:`~stubpy.context.StubContext` that is created fresh for every
call to :func:`~stubpy.generator.generate_stub`.

.. code-block:: text

   generate_stub(filepath)
       │
       ├─ 1. loader      load_module()                → module, path, name
       │        └─ (skipped in AST_ONLY; warning+fallback in AUTO)
       ├─ 2. ast_pass    ast_harvest()                → ASTSymbols
       ├─ 3. imports     scan_import_statements()     → import_map
       ├─ 4. aliases     build_alias_registry()       → ctx populated
       ├─ 5. symbols     build_symbol_table()         → SymbolTable
       ├─ 6. emitter     for each symbol (source order):
       │       ├─ AliasSymbol    → generate_alias_stub()
       │       ├─ ClassSymbol    → generate_class_stub()
       │       │       └─ for each method:
       │       │           resolver  resolve_params()
       │       │           emitter   generate_method_stub()  ← raw AST anns
       │       ├─ OverloadGroup → generate_overload_group_stub()
       │       ├─ FunctionSymbol → generate_function_stub()
       │       │       └─ resolver  resolve_function_params() ← AST targets + namespace
       │       └─ VariableSymbol → generate_variable_stub()
       ├─ 7. imports     collect_typing_imports()     → header
       │                 collect_special_imports()
       │                 collect_cross_imports()
       └─ 8. write       .pyi file written to disk


Stage 1 - Module loading
------------------------

:mod:`stubpy.loader` uses :func:`importlib.util.spec_from_file_location`
to load the source file as a live Python module.  The file's parent
directory *and* its grandparent are temporarily added to :data:`sys.path`
so that package-relative imports inside the target file resolve correctly,
then removed once loading completes.

This stage respects :class:`~stubpy.context.ExecutionMode`:

- **RUNTIME** (default) — execute the module; full introspection available.
- **AST_ONLY** — skip this stage entirely; live types will be ``None``.
  Useful for modules with import-time side effects or heavy dependencies.
- **AUTO** — attempt the load; on any exception, record a ``WARNING``
  diagnostic and continue with AST-only data.

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
``{local_name: import_statement}`` map of every import in the file,
including inline imports inside function bodies.  This map is used to:

- discover type-alias sub-modules (Stage 4),
- re-emit cross-file class imports in the ``.pyi`` header (Stage 7).

``from module import *`` statements are recorded under the reserved key
``"*"`` so callers can handle them explicitly.

Stage 4 - Alias registry
------------------------

:mod:`stubpy.aliases` scans the loaded module for imported sub-modules
(e.g. ``from demo import types``).  Any attribute of such a sub-module
that is a type alias — a PEP 604 union (``str | int``) or a subscripted
typing generic (``List[str]``, ``Literal["a"]``) — is registered in the
:class:`~stubpy.context.StubContext`.

When :func:`~stubpy.annotations.annotation_to_str` encounters a matching
annotation later, it emits ``types.Length`` instead of expanding it to
``str | float | int``.  This stage is a no-op when ``module`` is ``None``
(AST_ONLY mode).

Stage 5 - Symbol table
----------------------

:func:`~stubpy.symbols.build_symbol_table` merges the live module objects
from Stage 1 with the AST metadata from Stage 2 into a unified
:class:`~stubpy.symbols.SymbolTable`.

Each entry is a typed :class:`~stubpy.symbols.StubSymbol` subclass:

- :class:`~stubpy.symbols.AliasSymbol` — ``TypeAlias`` / ``NewType`` /
  ``TypeVar`` / ``ParamSpec`` / ``TypeVarTuple`` declaration.
- :class:`~stubpy.symbols.ClassSymbol` — live ``type`` object +
  :class:`~stubpy.ast_pass.ClassInfo` (bases, decorators, methods with
  raw annotations).
- :class:`~stubpy.symbols.FunctionSymbol` — callable + is_async flag.
- :class:`~stubpy.symbols.VariableSymbol` — live value + annotated or
  inferred type string.
- :class:`~stubpy.symbols.OverloadGroup` — multiple ``@overload``
  variants sharing one name.

If ``__all__`` was found in Stage 2, it is stored as a ``set[str]`` in
``ctx.all_exports`` and used to filter the symbol table to public names
only.

Stage 6 - Resolve and emit
--------------------------

Symbols are emitted in source-definition order from the symbol table.

**AliasSymbol** — :func:`~stubpy.emitter.generate_alias_stub` re-emits
the declaration verbatim from the AST pre-pass source string, preserving
TypeVar constraints, bounds, and TypeAlias right-hand sides.

**ClassSymbol** — :func:`~stubpy.emitter.generate_class_stub` uses
``__orig_bases__`` (PEP 560) rather than ``__bases__`` to emit base
classes, preserving subscripted generics such as ``Generic[T]``.
Special handling exists for ``@dataclass``, ``NamedTuple``, and abstract
base classes.

**OverloadGroup** — :func:`~stubpy.emitter.generate_overload_group_stub`
emits one ``@overload``-decorated stub per variant (per PEP 484).  The
concrete implementation stub is suppressed by the generator.

**FunctionSymbol / method** — :mod:`stubpy.resolver` implements the core
``**kwargs`` / ``*args`` backtracing logic via two entry points:

:func:`~stubpy.resolver.resolve_params` — *class methods*, using the MRO:

1. **No variadics** — return the method's own parameters unchanged.
2. **@classmethod cls() detection** — if the body contains
   ``cls(..., **kwargs)``, resolve against ``cls.__init__``.  Explicitly
   hardcoded keyword names are excluded to avoid duplicates.
3. **MRO walk** — iterate ancestors collecting concrete parameters until
   all variadics are resolved or the MRO is exhausted.

:func:`~stubpy.resolver.resolve_function_params` — *standalone functions*,
using pre-scanned AST forwarding targets:

1. **No variadics** — return own parameters unchanged.
2. **No targets** — variadics preserved as-is (no information to expand them).
3. **Target resolution** — look each name listed in
   :attr:`~stubpy.ast_pass.FunctionInfo.kwargs_forwarded_to` /
   ``args_forwarded_to`` up in the live module namespace.  Merge concrete
   parameters; recurse for chained forwarding; cycle-safe via a ``_seen``
   set.
4. **Default-ordering enforcement** — absorbed non-default params that follow
   a defaulted own-param are promoted to ``KEYWORD_ONLY``, keeping the stub
   syntactically valid.

Both resolvers share :func:`~stubpy.resolver._merge_concrete_params` and
:func:`~stubpy.resolver._finalise_variadics`.  ``POSITIONAL_ONLY`` parameters
absorbed via ``**kwargs`` are promoted to ``POSITIONAL_OR_KEYWORD`` by
:func:`~stubpy.resolver._normalise_kind`.

The AST body scan that populates ``kwargs_forwarded_to`` and
``args_forwarded_to`` runs during Stage 2 (the AST pre-pass) for every
function and method definition — including ``@classmethod`` bodies where
the ``cls(...)`` forwarding pattern is detected.  No second source parse is
needed at stub-emission time.

Both :func:`~stubpy.emitter.generate_method_stub` and
:func:`~stubpy.emitter.generate_function_stub` insert a bare ``/``
separator after the last positional-only parameter (PEP 570) and a bare
``*`` before the first keyword-only parameter where needed.

Stage 6a - Annotation conversion
---------------------------------

:mod:`stubpy.annotations` converts live annotation objects to stub-safe
strings via a *dispatch table* (not an if/elif chain).  Handlers include
``TypeVar`` / ``ParamSpec`` / ``TypeVarTuple`` (render as bare name,
avoiding the ``~T`` representation Python 3.12+ produces from ``str()``),
PEP 604 unions, subscripted generics, plain types, ``NoneType``, and more.

Stage 7 - Header assembly and write
------------------------------------

:mod:`stubpy.generator` assembles the file header:

- ``from __future__ import annotations``
- ``from typing import ...`` — scanned dynamically from ``typing.__all__``
  using whole-word boundary matching (no false positives such as ``List``
  matching inside ``BlackList``)
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
