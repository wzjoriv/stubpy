Changelog
=========

All notable changes to stubpy are recorded here.
The format follows `Keep a Changelog <https://keepachangelog.com/>`_.

0.6.0
-----

**Added**

- **Mixed method ↔ function forwarding chains** — ``**kwargs`` and ``*args``
  are now resolved across arbitrary mixed chains: method → function → method,
  function → class constructor → method, and any depth thereof.
  :func:`~stubpy.resolver.resolve_params` and
  :func:`~stubpy.resolver.resolve_function_params` now call each other when a
  forwarding target crosses the class/module boundary.  A shared ``_seen``
  frozenset prevents infinite recursion in mutually-recursive patterns.

- **Property MRO tracking** (GAP-14 closed) — when a subclass redefines only
  the getter of a property whose setter lives in a parent class (or
  vice-versa), the generated stub now emits both ``@property`` and
  ``@name.setter`` by walking the full MRO via the new
  :func:`~stubpy.emitter._find_property_mro` helper.

- **Incremental stub merge** (GAP-15 closed) — new :mod:`stubpy.stub_merge`
  module.  Setting ``incremental_update = true`` in ``stubpy.toml`` (or
  passing ``--incremental`` on the CLI) wraps generated content in
  ``# stubpy: auto-generated begin/end`` markers and merges only the marked
  region on subsequent runs, leaving manually edited content outside the
  markers untouched.  Marker matching is case-insensitive and whitespace-
  lenient.  Multiple marker pairs per file and half-open pairs are handled
  gracefully.

- **Docstring type inference** (GAP-11 partial, closed) — new
  :mod:`stubpy.docstring` module with parsers for NumPy, Google, and
  Sphinx/reST docstring conventions.  When ``infer_types = true`` is set (or
  ``--infer-types`` on the CLI), parameters and return types inferred from
  docstrings are emitted as ``# type: X`` inline comments — visually distinct
  from real annotations.  All three parsers run and their results are
  *merged*, so mixed-style docstrings receive full coverage.  Indented
  docstrings (the common case) are parsed correctly.

- **``ctx_factory`` file-info support in** :func:`~stubpy.generator.generate_package`
  — the factory callable now accepts either ``()`` or
  ``(source_path, output_path)`` signatures.  This lets callers customise the
  :class:`~stubpy.context.StubContext` per-file (e.g. use
  ``AST_ONLY`` for slow-importing modules, attach custom annotation handlers
  for specific subpackages, or set different output styles).

- **``@typing.type_check_only`` support** — classes decorated with
  ``@type_check_only`` now emit the ``@type_check_only`` decorator in the
  stub, correctly signalling to type checkers that the class is absent at
  runtime.

- **``@typing.dataclass_transform`` support** — factory classes decorated
  with ``@dataclass_transform`` now emit the decorator with its parameters in
  the stub (PEP 681).

- **CLI flags** — ``--infer-types`` enables docstring type inference;
  ``--incremental`` enables the stub-merge mode;
  ``--exclude PATTERN`` skips files matching a glob pattern during package
  processing (repeatable for multiple patterns, appended to any config-file
  ``exclude`` list); ``--no-respect-all`` stubs all symbols regardless of
  ``__all__``.

- **TOML config keys** — ``infer_types`` (alias: ``infer_types_from_docstrings``)
  and ``incremental`` (alias: ``incremental_update``) are now recognised in
  ``stubpy.toml`` / ``[tool.stubpy]``.  ``respect_all`` was already supported
  but is now also fully documented and exposed via ``--no-respect-all`` on the
  CLI.

- **``StubConfig`` fields** — ``infer_types_from_docstrings: bool`` (default
  ``False``) and ``incremental_update: bool`` (default ``False``).

- **Dynamic version** — ``pyproject.toml`` now uses ``dynamic = ["version"]``
  sourced from ``stubpy.__version__``.  Bumping the version in
  ``__init__.py`` automatically propagates to the package metadata.

- **Python 3.14 CI** — the GitHub Actions test matrix now includes Python
  3.14 (pre-release, ``allow-prereleases: true``) on all three OS targets.

- **New demo module** — ``demo/dispatch.py`` exercises method → function
  chains, property MRO inheritance, and docstring-only types.

- **Test restructure** — the ``tests/`` directory now mirrors ``stubpy/``'s
  module layout.  Previously scattered files (``test_function_resolver.py``,
  ``test_special_classes.py``, ``test_module_symbols.py``,
  ``test_property_mro.py``, ``test_mixed_chains.py``) were consolidated into
  ``test_resolver.py``, ``test_emitter.py``, and new ``test_generator.py``,
  ``test_main.py``, ``test_docstring.py``, and ``test_stub_merge.py``.
  Shared helpers and fixtures moved to ``conftest.py``.

**Fixed**

- **f-string syntax** in ``annotations.py`` (line 388) was invalid on
  Python 3.10 and 3.11 (nested quotes inside f-strings require Python 3.12+).
  Fixed by extracting ``", ".join(parts)`` to an intermediate variable.

- **Indented Google-style docstrings** were not parsed (section headers like
  ``    Args:`` with leading spaces were silently skipped).  The parser now
  detects the base indentation level of the docstring body and matches section
  headers relative to it.

- **Comma placement in multi-line stubs with inline comments** — the new
  ``_join_params_multiline`` helper ensures the trailing comma appears
  *before* any ``# type:`` comment, producing syntactically valid stubs.

- **Signature validity after namespace resolution** — ``_enforce_signature_validity``
  is now also applied in the MRO walk path, preventing invalid "non-default
  parameter follows default" errors when namespace-resolved parameters are
  absorbed.

**Docs**

- API reference cleaned up: duplicate "Full API reference" section removed,
  empty ``AST pre-pass`` / ``Symbol table`` / ``Emitters`` sub-sections
  replaced with substantive content and cross-links.

- New API pages for :mod:`stubpy.docstring` and :mod:`stubpy.stub_merge`.

**Known limitations (documented)**

- **Positionally-bound kwargs targets** — when a method forwards ``**kwargs``
  to a function via ``f(self.x, y, **kwargs)``, the resolver cannot detect
  that ``self.x`` positionally fills the first parameter of *f*.  All of
  *f*'s non-variadic parameters (including the positionally-bound ones)
  appear in the generated stub.  Workaround: pass the pre-bound argument
  by keyword (``f(x=self.x, **kwargs)``) or use explicit named parameters
  instead of ``**kwargs``.

- **Stub markers are file-level for** ``generate_stub`` — the
  ``incremental_update`` / ``--incremental`` flag wraps the *entire*
  generated stub.  Placing ``# stubpy: auto-generated begin/end`` markers
  inside class bodies is supported by the low-level
  :func:`~stubpy.stub_merge.merge_stubs` API but not by the
  ``generate_stub`` pipeline (which would inject a full file stub into the
  class body).

----

----

0.5.3
-----

**Added**

- **``--union-style`` flag** (renamed from ``--typing-style``)  — controls
  whether union annotations are emitted as ``X | None`` (``modern``, PEP 604,
  the default) or ``Optional[X]`` (``legacy``).  The rename makes the flag's
  scope unambiguous alongside ``--alias-style``.

- **``--include-docstrings`` / ``include_docstrings``** — when enabled,
  each function, method, and class stub receives the original docstring as a
  triple-quoted body instead of ``...``.  Useful when stubs double as
  quick-reference documentation for IDEs.

- **``register_annotation_handler(predicate)``** — public extension hook that
  appends a custom ``(annotation, ctx) → str`` handler to the dispatch table.
  Allows third-party libraries (Pydantic, attrs, beartype, …) to teach stubpy
  how to render their custom annotation types without forking the source.
  Exported from the top-level ``stubpy`` package.

- **Glob expansion in the CLI** — path arguments containing ``*``, ``?``,
  or ``[`` are expanded by Python's :func:`glob.glob` (``recursive=True``),
  so ``stubpy "src/*.py"`` and ``stubpy "**/*.py"`` work even when the shell
  does not expand the pattern.  Explicit paths without wildcards are unchanged.
  All combinations of files, directories, and glob patterns may be mixed in
  one invocation.

- **``TypedDict`` stub generation** — classes created with
  :func:`~typing.TypedDict` are now emitted as clean
  ``class Name(TypedDict):`` / ``class Name(TypedDict, total=False):`` blocks
  with per-field annotations, instead of falling through to the generic class
  path.

- **Enum stub generation** — :class:`~enum.Enum` and :class:`~enum.IntEnum`
  subclasses are emitted with the correct base class (``Enum``, ``IntEnum``,
  etc.) and ``from enum import …`` is injected automatically.  Internal
  implementation methods (``_generate_next_value_``, ``_missing_``, …) are
  suppressed from the stub.

- **Enum-valued defaults rendered correctly** — ``default_to_str`` now emits
  ``ClassName.MEMBER_NAME`` for Enum member defaults (e.g. ``BlendMode.NORMAL``)
  instead of the non-valid ``<BlendMode.NORMAL: 'normal'>`` repr.  Type
  objects used as defaults are rendered as their ``__name__``.

- **NamedTuple extra methods** — ``@property`` descriptors and ordinary
  methods defined on a NamedTuple subclass are now emitted in the stub.
  Auto-generated NamedTuple internals (``_make``, ``_asdict``, ``_replace``,
  ``__getnewargs__``) are suppressed.

- **Python 3.10 compatibility fixes in annotations**:

  - ``_UnionType`` guard — the ``types.UnionType`` check is wrapped in
    ``getattr`` so the annotations module imports without error on Python < 3.10
    where ``UnionType`` does not exist.
  - ``types.GenericAlias`` is now an explicit predicate in the dispatch table,
    so PEP 585 built-in subscripts (``list[int]``, ``tuple[str, ...]``) are
    always matched correctly before the generic ``__origin__`` catch-all.
  - ``typing.TypeVarTuple`` test skipped on Python < 3.11 where it is absent.

- **Expanded demo** — the demo package is now a coherent *PixelForge*
  graphics library with realistic module names:

  - ``demo/primitives.py`` — dataclass, NamedTuple, TypedDict, Enum, ABC +
    ``**kwargs`` MRO backtracing through ``Shape → Circle / Rect / Text``.
  - ``demo/scene.py`` — TypeVar, Generic[T], Generic[K,V], Protocol,
    TypeAlias, NewType, bound / constrained TypeVars.
  - ``demo/style.py`` — three-variant ``@overload``, generic overload,
    overloaded classmethod, GradientStop NamedTuple.
  - ``demo/export.py`` — cross-file imports, TYPE_CHECKING guard, async
    export, typed ``*args``.

- **CI: Python 3.14-dev** — the test matrix now includes a Python 3.14
  pre-release build on Ubuntu (``allow-prereleases: true``).  A separate
  ``coverage`` job uploads to Codecov; a ``docs`` job builds the HTML
  documentation and deploys to GitHub Pages on every push to ``main``.

**Fixed**

- ``_generate_namedtuple_stub`` was using ``repr()`` for field defaults,
  which produced broken stubs when a default contained quotes or was an
  Enum member.  Now uses ``default_to_str()``.

- ``collect_special_imports`` did not detect ``Enum`` / ``IntEnum`` /
  ``StrEnum`` base-class references in the stub body.  A ``from enum import
  …`` line is now injected automatically when any Enum subclass is emitted.

- ``__main__.py`` refactored into clearly-separated helper functions
  (``_build_parser``, ``_expand_paths``, ``_build_config``,
  ``_run_file``, ``_run_package``, ``_run_multi``) with no module-level
  side effects; ``glob`` moved to a module-level import.

- Dead ``all_diagnostics`` list in ``_run_package`` (collected but never
  printed) removed.

----

0.5.2
-----

**Added**

- **Function-level ``**kwargs`` / ``*args`` backtracing.**
  :func:`~stubpy.resolver.resolve_function_params` expands variadic parameters
  for **module-level functions** using AST-detected forwarding targets, exactly
  as :func:`~stubpy.resolver.resolve_params` does for class methods via the MRO.

  Two new fields on :class:`~stubpy.ast_pass.FunctionInfo` record where
  variadics are forwarded:
  :attr:`~stubpy.ast_pass.FunctionInfo.kwargs_forwarded_to` and
  :attr:`~stubpy.ast_pass.FunctionInfo.args_forwarded_to`.
  These are populated by a new body scan inside
  :meth:`~stubpy.ast_pass.ASTHarvester._harvest_function` — no extra source
  parse at emission time.

  All parameter kinds are handled:

  - ``/`` (positional-only) — promoted to ``POSITIONAL_OR_KEYWORD`` when
    absorbed via ``**kwargs`` (they can only be passed by keyword through the
    forwarding interface).
  - ``*args`` — preserved when unresolved or explicitly typed.
  - Keyword-only (after ``*`` or ``*args``) — merged and emitted with the
    bare ``*`` separator.
  - Residual ``**kwargs`` — kept only when the forwarding target itself still
    has ``**kwargs`` (the chain is still open).
  - Chained forwarding (``A → B → C``) — resolved recursively, with cycle
    detection to prevent infinite recursion.

  Example::

      # source
      def make_color(r: float, g: float, b: float, a: float = 1.0) -> Color: ...
      def make_red(r: float = 1.0, **kwargs) -> Color:
          return make_color(r=r, **kwargs)

      # generated stub — previously **kwargs was left unexpanded
      def make_red(r: float = 1.0, *, g: float, b: float, a: float = 1.0) -> Color: ...

- **Default-ordering enforcement.**
  When absorbed parameters would violate Python's rule that non-default
  parameters may not follow defaulted ones in the positional portion of a
  signature, stubpy automatically promotes the offending parameters to
  ``KEYWORD_ONLY`` (after a bare ``*``).  The new helper
  :func:`~stubpy.resolver._enforce_signature_validity` handles this for both
  the function resolver and the class-method MRO resolver.

- **Shared resolver infrastructure.**  Three new helpers used by both
  resolvers eliminate previously duplicated logic:
  :func:`~stubpy.resolver._merge_concrete_params`,
  :func:`~stubpy.resolver._finalise_variadics`, and
  :func:`~stubpy.resolver._enforce_signature_validity`.

- **``StubContext.module_namespace``** field.  The live module's ``__dict__``
  is stored on :class:`~stubpy.context.StubContext` after stage 1, making it
  accessible to downstream extension code.

- **Multi-file CLI.**  The ``stubpy`` command now accepts multiple paths::

      stubpy a.py b.py c.py
      stubpy src/*.py
      stubpy module.py mypackage/

  Paths may be any mix of ``.py`` files and package directories.  When more
  than one path is given, ``-o`` is silently ignored (a warning is printed to
  stderr); stubs are written alongside each source file.

- **64 new tests** in ``tests/test_function_resolver.py`` covering
  function-level resolution, AST body scanning, all parameter kinds, chained
  and recursive forwarding, cycle detection, default-ordering enforcement,
  ``*`` / ``/`` separator placement, multi-file CLI, and full demo-package
  integration.

- **Expanded demo** — ``demo/functions.py`` now exercises positional-only
  parameters (``/``), chained ``**kwargs`` forwarding, typed ``*args``,
  combined ``*args`` + ``**kwargs`` forwarding, and keyword-only parameters
  after ``*``.

**Fixed**

- ``SyntaxWarning: invalid escape sequence '\('`` in the
  ``_extract_locally_defined_names`` docstring in ``stubpy/imports.py``.

- **Duplicate-description Sphinx warnings** eliminated.  ``docs/api/public.rst``
  has been rewritten as a pure navigation / summary page (``autosummary``
  tables and cross-references only, zero ``autofunction`` / ``autoclass``
  directives).  All full API documentation lives in the per-module pages.
  ``:no-index:`` annotations removed from per-module pages now that they are
  the sole canonical source.

- **Duplicate ``changelog`` label** Sphinx warning.  The explicit
  ``.. _changelog:`` label in ``changelog.rst`` was removed — Sphinx
  generates a ``changelog`` anchor automatically from the toctree entry
  filename, making the hand-written label redundant.

- **RST formatting error** in ``docs/examples/project_integration.rst``:
  a section heading beginning with ``**kwargs`` was treated as an unclosed
  bold-emphasis node.  Rephrased using the inline-code form
  ````**kwargs``` to avoid the ambiguity.

----

----

0.5.1
-----

**Added**

- **``# stubpy: ignore`` directive.**  Place ``# stubpy: ignore`` (case-insensitive)
  at the top of any ``.py`` file (before any code) to exclude it from stub
  generation entirely.  The generator writes a minimal ``from __future__ import
  annotations`` stub and records an ``INFO`` diagnostic.  Useful for generated
  files, C extensions, or modules that are intentionally un-stubbed.

- **Implicit TypeAlias detection** for bare assignments without an explicit
  ``TypeAlias`` annotation.  Three patterns are now promoted to
  :class:`~stubpy.ast_pass.TypeVarInfo` entries during the AST pre-pass:

  - PEP 604 union RHS — ``Number = int | float``
  - Subscripted generic RHS — ``Length = Union[str, float, int]``,
    ``Items = list[int]``
  - Known built-in or typing type name — ``MyStr = str``, ``Count = int``,
    ``MyList = list``

  ``SomeArbitraryClass = OtherClass`` is intentionally NOT promoted (cannot
  determine at parse time whether ``OtherClass`` is a type or a value).

- **Python 3.12+ PEP 695 ``type`` statement support.**  The AST harvester
  now recognises ``type Vector = list[float]`` and ``type Stack[T] = list[T]``
  via a new ``visit_TypeAlias`` visitor method.  These are stored as
  :class:`~stubpy.ast_pass.TypeVarInfo` with ``kind="TypeAlias"``.

- **``alias_style`` configuration option** in
  :class:`~stubpy.context.StubConfig`.  Controls the output format for
  TypeAlias declarations:

  - ``"compatible"`` (default) — ``Name: TypeAlias = <rhs>``  (Python 3.10+)
  - ``"pep695"`` — ``type Name = <rhs>``  (Python 3.12+ only)
  - ``"auto"`` — selects ``pep695`` on Python 3.12+, otherwise ``compatible``

  Available via ``stubpy.toml``/``pyproject.toml`` and the new
  ``--alias-style`` CLI flag.

- **Compact variable/alias block spacing.**  Consecutive single-line stubs
  of the same kind (variables or type aliases) are now grouped without blank
  lines between them, matching the style of hand-written stubs.  A blank line
  still separates different symbol kinds (variable block → class, etc.).

- **``--alias-style`` CLI flag** — ``compatible``, ``pep695``, or ``auto``.

- **``ASTSymbols.skip_file``** field — ``True`` when the ``# stubpy: ignore``
  directive is found; read by the generator to skip emission.

**Fixed**

- **``variables.pyi`` missing ``from demo import types``** and equivalent
  variable-only files.  ``collect_cross_imports`` now detects lowercase dotted
  references (``types.Length``) in addition to capitalised annotation names.

- **False-positive typing imports** — ``container.pyi`` was incorrectly
  importing ``Container`` from :mod:`typing`; ``graphics.pyi`` imported ``Text``;
  ``element.pyi`` imported ``override``.  All were user-defined names in the same
  stub body.  :func:`~stubpy.imports.collect_typing_imports` now excludes names
  that are locally defined (classes, functions, parameter names) in the stub body.

- **Duplicate ``from demo import types``** in stubs where the same import was
  detected by both the alias-registry path and the new dotted-reference path.
  Stage 7 (header assembly) now uses an ordered-insertion deduplication set so
  any import statement can appear at most once, regardless of detection path.

- **``_emit_class`` NameError** causing empty stub bodies.  A bad str_replace
  in a previous edit accidentally embedded the ``_emit_class`` function body
  inside an unreachable path after ``return`` in ``_join_sections``.  Restored
  as a standalone function.

- **Phase reference** ("Phase 4 additions") removed from ``emitter.py`` module
  docstring.

**Changed**

- :func:`~stubpy.imports.collect_cross_imports` now performs two detection
  passes: capitalised annotation names (existing) and lowercase dotted module
  references (new).  Both passes share a single deduplication set.

- ``demo/types.py`` updated to use explicit ``TypeAlias`` annotations
  (``Number: TypeAlias = int | float``, etc.) for unambiguous stub output.

- Copyright year updated to 2026.

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

- **``union_style`` configuration option** in :class:`~stubpy.context.StubConfig`.
  ``"modern"`` (default) emits PEP 604 ``X | None`` syntax; ``"legacy"``
  emits ``Optional[X]`` / ``Union[X, Y]`` for compatibility with older
  type checkers.  Applies to both the PEP 604 ``UnionType`` handler and
  the ``typing.Union`` branch of the generic handler.

- **``exclude`` and ``output_dir`` fields** on :class:`~stubpy.context.StubConfig`.
  ``exclude`` is a list of glob patterns (matched against relative POSIX paths)
  for files to skip during package processing.  ``output_dir`` is the default
  output root for ``generate_package`` when none is specified on the CLI.

- **New CLI flags**: ``--execution-mode`` (``runtime`` / ``ast_only`` /
  ``auto``), ``--union-style`` (``modern`` / ``legacy``), and ``--no-config``
  (skip config-file lookup).  The ``path`` positional argument now accepts
  either a ``.py`` file or a directory; a directory triggers package mode.

- **``PackageResult``** dataclass (in :mod:`stubpy.generator`) with
  ``stubs_written``, ``failed``, and ``summary()`` members.

**Changed**

- ``"modern"`` is now the **default** ``union_style``.  Stubs generated
  without explicit configuration now emit ``str | None`` instead of
  ``Optional[str]``.  Tests that asserted the old ``Optional[str]`` form
  have been updated; callers that need the legacy form should set
  ``StubConfig(union_style="legacy")``.

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
