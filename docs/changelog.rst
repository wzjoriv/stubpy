.. _changelog:

Changelog
=========

All notable changes to stubpy are recorded here.
The format follows `Keep a Changelog <https://keepachangelog.com/>`_.

----
0.2.1 - 2026-04-01
--------------------------
**Added**

- ``include_private`` is accepted as a parameter in cli.
- ``generate_function_stub`` is now part of ``emitter.py``.


0.2.0 - 2026-03-28
--------------------------

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
  ``symbol_table``, ``all_exports``.  All existing code calling
  ``StubContext()`` with no arguments continues to work unchanged.

- :func:`~stubpy.loader.load_module` gains an optional ``diagnostics``
  parameter; load errors are recorded in the collector before being
  re-raised.

**Fixed**

- ``Ellipsis`` sentinel (``...``) now renders as ``"..."`` in stubs.
  Previously ``annotation_to_str(...)`` fell through to ``str(...)`` which
  returns ``"Ellipsis"``, producing broken ``Tuple[int, Ellipsis]`` output.
  Added a dedicated ``@_register(lambda a: a is ...)`` dispatch handler.

- Type-alias preservation across ``Optional`` / ``| None`` unions: when
  ``Color = Union[str, Tuple[...]]`` and a parameter is annotated
  ``stroke: Color | None``, Python constructs a new ``Union`` whose args
  include ``NoneType`` — losing the ``Color`` boundary.  The
  ``_handle_generic`` and ``_handle_pep604_union`` handlers now reconstruct
  the non-``None`` sub-union and check the alias registry on it, emitting
  ``Optional[types.Color]`` or ``types.Color | None`` instead of the raw
  expansion.

- Type-alias preservation in mixed-union parameters (``Union[types.Color, int]``
  etc.): Python's ``typing.Union`` flattens such expressions at evaluation
  time, permanently losing alias boundaries.  The AST pre-pass stores the
  raw annotation string before evaluation; ``format_param`` now accepts a
  ``raw_ann_override`` argument and uses it when the string references a
  registered alias module prefix, bypassing the flattened runtime annotation.

- ``from pkg import types`` header import was silently dropped when the
  raw-annotation override path was taken in ``format_param``.  Fixed by
  explicitly populating ``ctx.used_type_imports`` for every alias module
  referenced in the raw string.

- ``✓`` checkmark in ``__main__.py`` CLI output replaced with ``"Stub written
  to:"`` to avoid ``UnicodeEncodeError`` on Windows ``cp1252`` terminals.

- Unused imports removed from ``emitter.py`` (``_VAR_KW``), ``loader.py``
  (``DiagnosticLevel`` in inline imports), and ``__main__.py``
  (``ExecutionMode``, ``DiagnosticLevel``).

**Changed**

- Pipeline extended from 6 to 9 stages: AST pre-pass (stage 2) and symbol
  table assembly (stage 5) are now explicit steps inside ``generate_stub``.
  The ``StubContext`` carries the populated ``SymbolTable`` and ``all_exports``
  set after these stages complete.

- Test suite expanded from 235 to 435+ tests across 11 test modules, adding
  full coverage for all Phase 1 modules.

----

0.1.1 - 2026-03-15
------------------

**Fixed**

- ``*args`` ordering bug in ``_resolve_via_mro``: when a child class had
  both typed ``*args`` and ``**kwargs``, ``*args`` was incorrectly placed
  *after* any already-appended ``**kwargs``, producing invalid Python
  syntax (e.g. ``def f(label, **kwargs, *items)``). Fixed by inserting
  ``*args`` before the first keyword-only parameter **and** before any
  trailing ``**kwargs``, then appending ``**kwargs`` afterward.
- ``__qualname__`` replaced with ``__name__`` in ``annotation_to_str``
  (``_handle_plain_type``) and ``generate_class_stub``. Using
  ``__qualname__`` caused test-local classes to emit their full nested
  scope path (e.g. ``TestFoo.test_bar.<locals>.MyClass``) instead of the
  simple name ``MyClass``.
- Fixed duplicate autodoc warnings in Sphinx build caused by
  ``api/public.rst`` re-declaring symbols already documented in their
  own module pages. ``public.rst`` now uses cross-references only.
- Fixed ``resolver.rst`` reStructuredText ``*args`` emphasis warning by
  escaping the leading ``*``.

**Added**

- New edge-case tests in ``tests/test_integration.py``:
  ``TestStaticMethods`` (5 tests) and ``TestArgsAndKwargsTogether``
  (6 tests) covering ``*args`` + ``**kwargs`` in all inheritance
  combinations.
- Updated ``docs/examples/kwargs_backtracing.rst`` with all new
  ``*args`` / ``**kwargs`` edge cases documented with worked examples.

**Changed**

- Private symbols (``_is_type_alias``, ``_register``, ``_detect_cls_call``,
  ``_resolve_via_cls_call``, ``_resolve_via_mro``, ``_get_raw_params``,
  ``_KW_SEP_NAME``, ``_PUBLIC_DUNDERS``, ``_TYPING_CANDIDATES``,
  ``_SKIP_IMPORT_PREFIXES``) removed from the public-facing API reference
  docs. Docstrings are retained in source for contributors.

----

0.1.0 - 2026-03-15
------------------

Initial release.

**Added**

- ``generate_stub(filepath, output_path)`` — main public API.
- ``stubpy`` CLI with ``-o / --output`` and ``--print`` flags.
- ``**kwargs`` backtracing via full MRO walk.
- ``*args`` backtracing with explicit-annotation preservation.
- ``@classmethod cls(**kwargs)`` detection via AST; resolves against
  ``cls.__init__`` rather than MRO siblings.
- Type-alias preservation for imported type sub-modules
  (``from pkg import types`` pattern).
- Cross-file import re-emission in ``.pyi`` headers.
- Keyword-only ``*`` separator inserted automatically.
- Inline formatting for ≤ 2 params; multi-line with trailing commas for
  larger signatures.
- ``StubContext`` dataclass replacing module-level globals — fully
  re-entrant.
- Dispatch-table ``annotation_to_str`` — extensible without editing a
  chain.
- Support for: plain types, PEP 604 unions, ``Optional``, ``Union``,
  ``Callable``, ``Literal``, ``Tuple``, ``List``, ``Dict``, ``Sequence``,
  ``Set``, ``FrozenSet``, ``Type``, ``ClassVar``, forward references,
  ``@property`` (with setter), ``@classmethod``, ``@staticmethod``.
- Complete pytest test suite (224 tests across 6 modules).
- Sphinx documentation with Furo theme.
