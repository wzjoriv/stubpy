.. _changelog:

Changelog
=========

All notable changes to stubpy are recorded here.
The format follows `Keep a Changelog <https://keepachangelog.com/>`_.

----

0.5.0
-----

**Added**

- **Package batch generation** (:func:`~stubpy.generator.generate_package`).
  Recursively stubs every ``.py`` file in a directory tree, mirrors the
  structure under an output directory, and creates ``__init__.pyi`` markers
  for every sub-package.  Files that fail are collected in
  :class:`~stubpy.generator.PackageResult` rather than aborting the run.
  ``generate_package`` lives in :mod:`stubpy.generator` alongside
  ``generate_stub`` — both functions share the same concern and the same
  module.

- **Configuration file support** (:mod:`stubpy.config`).
  stubpy now searches upward from the target path for a ``stubpy.toml``
  or a ``[tool.stubpy]`` section in ``pyproject.toml``.  On Python 3.11+
  the stdlib :mod:`tomllib` is used; on Python 3.10 the ``tomli`` backport
  is tried with a minimal hand-rolled fallback for the simple key/value
  syntax stubpy needs.  Config file values are overridden by CLI flags.

- **``typing_style`` configuration option** in :class:`~stubpy.context.StubConfig`.
  ``"modern"`` (default) emits PEP 604 ``X | None`` syntax; ``"legacy"``
  emits ``Optional[X]`` / ``Union[X, Y]`` for compatibility with older
  type checkers.  Applies to both the PEP 604 ``UnionType`` handler and
  the ``typing.Union`` branch of the generic handler.

- **``exclude`` and ``output_dir`` fields** on :class:`~stubpy.context.StubConfig`.
  ``exclude`` is a list of glob patterns (matched against relative POSIX paths)
  for files to skip during package processing.  ``output_dir`` is the default
  output root for ``generate_package`` when none is specified on the CLI.

- **New CLI flags**: ``--execution-mode`` (``runtime`` / ``ast_only`` /
  ``auto``), ``--typing-style`` (``modern`` / ``legacy``), and ``--no-config``
  (skip config-file lookup).  The ``path`` positional argument now accepts
  either a ``.py`` file or a directory; a directory triggers package mode.

- **``PackageResult``** dataclass (in :mod:`stubpy.generator`) with
  ``stubs_written``, ``failed``, and ``summary()`` members.

**Changed**

- ``"modern"`` is now the **default** ``typing_style``.  Stubs generated
  without explicit configuration now emit ``str | None`` instead of
  ``Optional[str]``.  Tests that asserted the old ``Optional[str]`` form
  have been updated; callers that need the legacy form should set
  ``StubConfig(typing_style="legacy")``.

- :func:`~stubpy.generator.generate_stub` gained a ``FileNotFoundError``
  guard at the top of the function (before any I/O) so the error is always
  recorded in the diagnostic collector before being re-raised.

**Fixed**

- :class:`~stubpy.context.StubContext` attributes no longer produce Sphinx
  ``duplicate object description`` warnings.  ``context.rst`` now uses
  ``:no-index:`` on ``autoclass`` directives and ``:exclude-members:`` on
  ``StubContext`` to prevent duplication.

----

0.4.0
-----

**Added**

- **TypeVar / TypeAlias / NewType / ParamSpec / TypeVarTuple re-emission.**
  Module-level declarations of these forms are now preserved in the generated
  stub verbatim from the AST pre-pass.  Previously they were silently dropped.
  A new :func:`~stubpy.emitter.generate_alias_stub` function handles emission
  for all alias-like symbols.

- **Generic base class preservation** (``Generic[T]``, ``Generic[K, V]``, etc.).
  :func:`~stubpy.emitter.generate_class_stub` now reads ``__orig_bases__``
  (PEP 560) in preference to ``__bases__``.  This preserves subscript
  information that ``__bases__`` erases — ``Generic[T]`` was previously
  collapsed to just ``Generic``.

- **TypeVar / ParamSpec / TypeVarTuple annotation rendering.**
  A new dispatch handler in :mod:`stubpy.annotations` converts ``TypeVar``,
  ``ParamSpec``, and ``TypeVarTuple`` objects to their bare name (e.g. ``T``).
  Python 3.12+ renders these objects as ``~T`` via ``str()``; the new handler
  is consistent across Python 3.10–3.13.

- **@overload stubs.**
  ``@overload``-decorated module-level functions are now collected as an
  :class:`~stubpy.symbols.OverloadGroup` and emitted with one
  ``@overload`` stub per variant via
  :func:`~stubpy.emitter.generate_overload_group_stub`.
  The concrete implementation stub is suppressed per PEP 484 convention.

- **Positional-only ``/`` separator (PEP 570).**
  :func:`~stubpy.emitter.insert_pos_separator` inserts a bare ``/`` sentinel
  after the last ``POSITIONAL_ONLY`` parameter.  Both
  :func:`~stubpy.emitter.generate_method_stub` and
  :func:`~stubpy.emitter.generate_function_stub` now emit ``/`` where
  required.

- **Positional-only parameter normalisation in MRO backtracing.**
  When a parent method's ``POSITIONAL_ONLY`` parameters are absorbed by a
  child's ``**kwargs``, the resolver now promotes them to
  ``POSITIONAL_OR_KEYWORD``.  Emitting them as positional-only in the child
  stub would have produced invalid Python (a misplaced ``/``).

- **``from module import *`` support in import scanner.**
  :func:`~stubpy.imports.scan_import_statements` now records star-import
  statements under the reserved key ``"*"`` so callers can handle them
  explicitly rather than silently discarding them.

- **Dynamic typing-import coverage.**
  :func:`~stubpy.imports.collect_typing_imports` now scans
  ``typing.__all__`` at import time instead of a hard-coded 14-name tuple.
  This automatically picks up names added in future Python releases.
  Matching uses whole-word ``\\b`` boundaries to avoid false positives
  (e.g. ``List`` no longer matches inside ``BlackList``).

- **AST_ONLY and AUTO execution modes fully wired.**
  :func:`~stubpy.generator.generate_stub` now correctly skips module
  execution in ``AST_ONLY`` mode and falls back gracefully to AST-only on
  load failure in ``AUTO`` mode.  Previously these modes were defined but not
  fully implemented in the generator pipeline.

- **New public emitter functions.**
  :func:`~stubpy.emitter.generate_alias_stub` and
  :func:`~stubpy.emitter.generate_overload_group_stub` are now exported from
  :mod:`stubpy` and available as part of the extension API.

**Fixed**

- :func:`~stubpy.aliases.build_alias_registry` raised ``TypeError`` when
  called with ``module=None`` (e.g. in ``AST_ONLY`` mode).  It now returns
  early without error.

- :func:`~stubpy.generator.generate_stub` did not read source before the
  stage-1 load block, causing ``FileNotFoundError`` to bypass the diagnostic
  recorder.  The path existence check is now done once up-front and raises
  ``FileNotFoundError`` consistently before any I/O.

- Pre-existing test ``test_inline_import_not_duplicated`` referenced a
  non-existent ``demo_module``.  It now uses ``ExecutionMode.AUTO`` with a
  sentinel module name to exercise the deduplication path without requiring
  a real importable module.

**Changed**

- :func:`~stubpy.generator.generate_stub` Stage 6 now dispatches to
  :func:`~stubpy.emitter.generate_alias_stub` for
  :class:`~stubpy.symbols.AliasSymbol` entries and to
  :func:`~stubpy.emitter.generate_overload_group_stub` for
  :class:`~stubpy.symbols.OverloadGroup` entries.  The placeholder comment
  ``# AliasSymbol and OverloadGroup are handled in future work`` has been
  removed.

- :mod:`stubpy.imports` module docstring updated to reflect dynamic
  ``typing.__all__`` scanning and star-import support.

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
