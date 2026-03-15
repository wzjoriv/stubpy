.. _changelog:

Changelog
=========

All notable changes to stubpy are recorded here.
The format follows `Keep a Changelog <https://keepachangelog.com/>`_.

----

0.1.1 — 2026-03-15
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

0.1.0 — 2026-03-15
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
