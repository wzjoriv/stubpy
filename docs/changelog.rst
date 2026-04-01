.. _changelog:

Changelog
=========

All notable changes to stubpy are recorded here.
The format follows `Keep a Changelog <https://keepachangelog.com/>`_.

----

0.3.1
-----

**Fixed**

- ``--include-private`` had no effect when the target module declared
  ``__all__``.  Private names were passing the ``include_private`` gate
  but then being incorrectly filtered out by the ``__all__`` check in
  ``build_symbol_table._include()``.  Private names are now controlled
  *solely* by ``include_private`` and bypass ``__all__`` entirely, while
  ``__all__`` continues to restrict which *public* names are emitted.

- Stale contradicting assertion removed from
  ``TestVariableHarvest.test_private_variable_skipped`` that was left over
  from a bad merge (lines 199-201 correctly asserted all names are harvested;
  line 202 immediately contradicted them).

**Added**

- ``demo/container.py`` — ``Container`` gains ``get()`` and ``clone()``
  methods; ``Layer`` gains ``lock()``, ``unlock()``, ``hide()``,
  ``show_layer()`` methods and a ``label`` keyword-only parameter.

- ``demo/element.py`` — ``Element`` is now an abstract base class
  (``class Element(ABC):``) with ``@abstractmethod`` on ``render`` and
  ``bounding_box``; ``Transform(NamedTuple)`` is exported.

- ``tests/test_integration.py`` — ``TestInlineImports`` documents and
  tests inline-import (inside function / method bodies) discovery and
  re-emission behaviour.

**Notes**

- Inline imports (imports placed inside function or method bodies to break
  circular dependencies) are fully supported.  ``scan_import_statements``
  uses ``ast.walk`` across the entire source file, so inline imports are
  discovered.  An inline import is re-emitted in the ``.pyi`` header when
  and only when the imported name actually appears in a stub annotation
  (return type, parameter type, base class, etc.).

0.3.0
-----

**Added**

- Module-level function stubs: ``generate_stub`` now emits ``def`` and
  ``async def`` stubs for every top-level function, not just class methods.
  The same inline / multi-line formatting and ``**kwargs`` back-tracing used
  for class methods applies here too.

- Module-level variable stubs: annotated variables (``x: int = 1``) emit
  ``name: Type`` stubs.  Unannotated assignments fall back to
  ``type(value).__name__`` from the runtime value, with a ``WARNING``
  diagnostic recorded.

- ``__all__`` filtering: when the target module declares ``__all__``,
  :func:`~stubpy.generator.generate_stub` includes only the named symbols.
  Applies to classes, functions, and variables uniformly.  Filtering is
  handled once in :func:`~stubpy.symbols.build_symbol_table` rather than
  scattered across the pipeline.

- ``--include-private`` CLI flag: includes symbols whose names start with
  ``_``.  Wired through :class:`~stubpy.context.StubConfig` and
  :class:`~stubpy.context.StubContext`.

- ``async def`` detection on class methods: :func:`~stubpy.emitter.generate_method_stub`
  now prefixes stubs with ``async`` when
  :func:`inspect.iscoroutinefunction` or :func:`inspect.isasyncgenfunction`
  returns ``True`` for the underlying callable.  Applies to regular methods,
  classmethods, staticmethods, and async generators.

- ``@abstractmethod`` support: abstract callables (those with
  ``__isabstractmethod__ = True``) emit ``@abstractmethod`` in their stub.
  Decorator stacking order is correct: ``@classmethod`` / ``@staticmethod``
  first, then ``@abstractmethod``.  Abstract properties emit
  ``@abstractmethod`` before ``@property``.

- ``@dataclass`` support: decorated classes emit the ``@dataclass`` decorator
  line and a synthesised ``__init__`` built from ``__dataclass_fields__``.
  ``ClassVar`` and ``init=False`` fields are excluded from the signature;
  ``default_factory`` fields are shown as ``field: Type = ...``.  Inherited
  field types are resolved through the MRO.  ``__post_init__`` is included
  in :data:`~stubpy.emitter._PUBLIC_DUNDERS`.

- ``NamedTuple`` support: NamedTuple subclasses emit
  ``class Name(NamedTuple):`` with per-field annotations and defaults.
  Auto-generated methods (``_make``, ``_asdict``, ``_replace``) are omitted.

- :func:`~stubpy.imports.collect_special_imports`: scans the generated stub
  body for ``@abstractmethod``, ``ABC``, and ``@dataclass`` and returns the
  corresponding ``from abc import …`` / ``from dataclasses import …``
  statements needed in the header.

- ``NamedTuple`` added to ``_TYPING_CANDIDATES`` so it is auto-imported when
  present in the stub body.

- New ``ctx`` parameter on :func:`~stubpy.generator.generate_stub`: callers
  can pass a pre-configured :class:`~stubpy.context.StubContext` (e.g. with
  custom :class:`~stubpy.context.StubConfig`) instead of relying on the
  internal default.

**Changed**

- The AST harvester (:class:`~stubpy.ast_pass.ASTHarvester`) is now a pure
  collector — it gathers *all* names, including private ones.  Private-name
  filtering is handled exclusively by
  :func:`~stubpy.symbols.build_symbol_table` via the ``include_private``
  parameter.  This is necessary for ``--include-private`` to work correctly.

- :func:`~stubpy.symbols.build_symbol_table` gains an ``include_private``
  parameter (default ``False``).

- Stub emission is now driven by
  ``ctx.symbol_table.sorted_by_line()`` in a single loop, so classes,
  functions, and variables always appear in source-definition order
  regardless of their kind.

- ``__all__`` is read from the AST pre-pass with a runtime ``module.__all__``
  fallback; it is no longer applied in the emitter but exclusively in
  ``build_symbol_table``.

- ``_SKIP_IMPORT_PREFIXES`` extended with ``"from dataclasses"`` so
  dataclasses imports are not incorrectly re-emitted as cross-module imports.

- Test suite expanded with two new pytest modules:
  ``tests/test_module_symbols.py`` and ``tests/test_special_classes.py``.

----

0.2.0
-----

**Added**

- ``stubpy/diagnostics.py`` — :class:`~stubpy.diagnostics.DiagnosticCollector`
  replaces bare ``try/except pass`` blocks throughout the pipeline.  Every
  stage records :class:`~stubpy.diagnostics.Diagnostic` entries with a
  :class:`~stubpy.diagnostics.DiagnosticLevel` (``INFO`` / ``WARNING`` /
  ``ERROR``) and a :class:`~stubpy.diagnostics.DiagnosticStage` identifying
  which pipeline stage raised the issue.

- ``stubpy/ast_pass.py`` — :func:`~stubpy.ast_pass.ast_harvest` performs a
  read-only :class:`ast.NodeVisitor` pass over the source *before* the module
  is executed, collecting top-level class definitions (with base-class and
  decorator lists), sync and async function definitions (with raw annotations),
  annotated variables, ``__all__``, and ``TypeVar`` / ``TypeAlias`` /
  ``ParamSpec`` / ``TypeVarTuple`` / ``NewType`` declarations.  Results are
  stored in :class:`~stubpy.ast_pass.ASTSymbols`.

- ``stubpy/symbols.py`` — :class:`~stubpy.symbols.SymbolTable` replaces the
  ad-hoc ``list[type]`` previously used to track classes.  Each entry is a
  :class:`~stubpy.symbols.StubSymbol` subclass:

  - :class:`~stubpy.symbols.ClassSymbol` — live ``type`` + AST metadata
  - :class:`~stubpy.symbols.FunctionSymbol` — callable + AST function node + ``is_async`` flag
  - :class:`~stubpy.symbols.VariableSymbol` — module-level variable with annotated or inferred type
  - :class:`~stubpy.symbols.AliasSymbol` — ``TypeAlias`` / ``NewType`` declaration
  - :class:`~stubpy.symbols.OverloadGroup` — multiple ``@overload`` variants sharing a name

- ``--verbose`` CLI flag: print all ``INFO``, ``WARNING``, and ``ERROR``
  diagnostics to ``stderr`` after generation.

- ``--strict`` CLI flag: exit with code ``1`` if any ``ERROR``-level
  diagnostic was recorded during the run, even when the stub file was
  written successfully.

- :class:`~stubpy.context.StubConfig` — per-run configuration dataclass
  (``execution_mode``, ``include_private``, ``respect_all``, ``verbose``,
  ``strict``).

- :class:`~stubpy.context.ExecutionMode` enum — ``RUNTIME`` / ``AST_ONLY``
  / ``AUTO`` controls whether the target module is executed.

- ``StubContext`` gains four new fields: ``config``, ``diagnostics``,
  ``symbol_table``, ``all_exports``.

- :func:`~stubpy.loader.load_module` gains an optional ``diagnostics``
  parameter; load errors are recorded in the collector before being
  re-raised.

**Fixed**

- ``Ellipsis`` sentinel (``...``) now renders as ``"..."`` in stubs.

- Type-alias preservation across ``Optional`` / ``| None`` unions.

- Type-alias preservation in mixed-union parameters
  (``Union[types.Color, int]``).

- ``from pkg import types`` header import was silently dropped when the
  raw-annotation override path was taken in ``format_param``.

- ``✓`` checkmark in CLI output replaced with plain text to avoid
  ``UnicodeEncodeError`` on Windows terminals.

**Changed**

- Pipeline extended from 6 to 9 stages: AST pre-pass (stage 2) and symbol
  table assembly (stage 5) are now explicit steps inside ``generate_stub``.

----

0.1.1
-----

**Fixed**

- ``*args`` ordering bug in ``_resolve_via_mro``: when a child class had
  both typed ``*args`` and ``**kwargs``, ``*args`` was incorrectly placed
  *after* any already-appended ``**kwargs``, producing invalid Python
  syntax.

- ``__qualname__`` replaced with ``__name__`` in ``annotation_to_str``
  and ``generate_class_stub``.

- Fixed duplicate autodoc warnings in Sphinx build.

- Fixed ``resolver.rst`` reStructuredText ``*args`` emphasis warning.

**Added**

- New edge-case tests in ``tests/test_integration.py``:
  ``TestStaticMethods`` and ``TestArgsAndKwargsTogether``.

**Changed**

- Private symbols removed from public-facing API reference docs.

----

0.1.0
-----

Initial release.

**Added**

- ``generate_stub(filepath, output_path)`` — main public API.
- ``stubpy`` CLI with ``-o / --output`` and ``--print`` flags.
- ``**kwargs`` backtracing via full MRO walk.
- ``*args`` backtracing with explicit-annotation preservation.
- ``@classmethod cls(**kwargs)`` detection via AST.
- Type-alias preservation for imported type sub-modules.
- Cross-file import re-emission in ``.pyi`` headers.
- Keyword-only ``*`` separator inserted automatically.
- Inline formatting for ≤ 2 params; multi-line with trailing commas.
- ``StubContext`` dataclass — fully re-entrant.
- Dispatch-table ``annotation_to_str`` — extensible without editing a chain.
- Support for all common annotation forms.
- Complete pytest test suite.
- Sphinx documentation with Furo theme.
