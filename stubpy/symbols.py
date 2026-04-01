"""
stubpy.symbols
==============

Symbol table — the unified data model for one stub-generation pass.

A :class:`SymbolTable` holds an ordered collection of :class:`StubSymbol`
entries, one per public name in the target module.  Each entry carries
both the live runtime object (when available from
:func:`~stubpy.loader.load_module`) and the AST metadata harvested by
:mod:`stubpy.ast_pass`.

Using a single symbol table as the shared data model eliminates the
implicit coupling that existed between ``collect_classes()`` and the rest
of the pipeline: every future pipeline stage reads and writes the same
table rather than maintaining parallel, ad-hoc data structures.

Symbol hierarchy
----------------

* :class:`StubSymbol` — base dataclass
    * :class:`ClassSymbol` — a ``class`` definition
    * :class:`FunctionSymbol` — a top-level ``def`` or ``async def``
    * :class:`VariableSymbol` — a module-level annotated variable
    * :class:`AliasSymbol` — ``TypeAlias`` / ``TypeVar`` / ``NewType`` etc.
    * :class:`OverloadGroup` — multiple ``@overload`` variants of one name

Examples
--------
>>> from stubpy.symbols import SymbolTable, ClassSymbol, SymbolKind
>>> tbl = SymbolTable()
>>> tbl.add(ClassSymbol(name="Foo", lineno=1))
>>> tbl.get("Foo").name
'Foo'
>>> tbl.get("Missing") is None
True
"""
from __future__ import annotations

import inspect
import types as _builtin_types
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator

from .ast_pass import ASTSymbols, ClassInfo, FunctionInfo, TypeVarInfo, VariableInfo


# ---------------------------------------------------------------------------
# Kind enumeration
# ---------------------------------------------------------------------------

class SymbolKind(Enum):
    """Category of a stub symbol."""
    CLASS     = "class"
    FUNCTION  = "function"
    VARIABLE  = "variable"
    ALIAS     = "alias"
    OVERLOAD  = "overload"


# ---------------------------------------------------------------------------
# Symbol classes
# ---------------------------------------------------------------------------

@dataclass
class StubSymbol:
    """
    Base dataclass for all stub symbols.

    Parameters
    ----------
    name : str
    kind : SymbolKind
    lineno : int
        Source line of the definition (used for sort-order in the stub).
    """
    name:   str
    kind:   SymbolKind
    lineno: int


@dataclass
class ClassSymbol(StubSymbol):
    """
    A class definition, combining runtime type with AST metadata.

    Parameters
    ----------
    live_type : type or None
        The runtime class object from :func:`~stubpy.loader.load_module`.
        ``None`` in AST-only mode.
    ast_info : ClassInfo or None
        Metadata from :class:`~stubpy.ast_pass.ASTHarvester`.

    Examples
    --------
    >>> sym = ClassSymbol(name="Widget", lineno=5)
    >>> sym.kind
    <SymbolKind.CLASS: 'class'>
    """
    live_type: type | None         = None
    ast_info:  ClassInfo | None    = None

    def __init__(
        self,
        name: str,
        lineno: int,
        live_type: type | None = None,
        ast_info: ClassInfo | None = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.CLASS, lineno=lineno)
        self.live_type = live_type
        self.ast_info  = ast_info


@dataclass
class FunctionSymbol(StubSymbol):
    """
    A top-level function definition, combining runtime callable + AST info.

    Parameters
    ----------
    live_func : callable or None
        The runtime function object. ``None`` in AST-only mode.
    ast_info : FunctionInfo or None
        Metadata from :class:`~stubpy.ast_pass.ASTHarvester`.
    is_async : bool
        Derived from *ast_info* when available; defaults to ``False``.

    Examples
    --------
    >>> sym = FunctionSymbol(name="greet", lineno=3, is_async=True)
    >>> sym.kind
    <SymbolKind.FUNCTION: 'function'>
    >>> sym.is_async
    True
    """
    live_func: Any | None            = None
    ast_info:  FunctionInfo | None   = None
    is_async:  bool                  = False

    def __init__(
        self,
        name:      str,
        lineno:    int,
        live_func: Any | None          = None,
        ast_info:  FunctionInfo | None = None,
        is_async:  bool                = False,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.FUNCTION, lineno=lineno)
        self.live_func = live_func
        self.ast_info  = ast_info
        # Prefer ast_info flag when provided
        self.is_async  = ast_info.is_async if ast_info is not None else is_async


@dataclass
class VariableSymbol(StubSymbol):
    """
    A module-level variable or constant.

    Parameters
    ----------
    live_value : Any
        The runtime value of the variable. ``None`` in AST-only mode or
        when the variable evaluates to ``None``.
    annotation_str : str or None
        Type annotation as an unparsed string, from the AST.
    inferred_type_str : str or None
        ``type(live_value).__name__`` when no annotation is available.
    ast_info : VariableInfo or None

    Examples
    --------
    >>> sym = VariableSymbol(name="MAX", lineno=1, annotation_str="int")
    >>> sym.kind
    <SymbolKind.VARIABLE: 'variable'>
    """
    live_value:        Any               = None
    annotation_str:    str | None        = None
    inferred_type_str: str | None        = None
    ast_info:          VariableInfo | None = None

    def __init__(
        self,
        name:              str,
        lineno:            int,
        live_value:        Any                = None,
        annotation_str:    str | None         = None,
        inferred_type_str: str | None         = None,
        ast_info:          VariableInfo | None = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.VARIABLE, lineno=lineno)
        self.live_value        = live_value
        self.annotation_str    = annotation_str
        self.inferred_type_str = inferred_type_str
        self.ast_info          = ast_info

    @property
    def effective_type_str(self) -> str | None:
        """Return annotation_str if available, else inferred_type_str."""
        return self.annotation_str or self.inferred_type_str


@dataclass
class AliasSymbol(StubSymbol):
    """
    A ``TypeAlias``, ``TypeVar``, ``ParamSpec``, ``TypeVarTuple``, or
    ``NewType`` declaration.

    Parameters
    ----------
    ast_info : TypeVarInfo or None
    live_obj : Any
        The runtime object, if available.

    Examples
    --------
    >>> sym = AliasSymbol(name="T", lineno=1)
    >>> sym.kind
    <SymbolKind.ALIAS: 'alias'>
    """
    ast_info: TypeVarInfo | None = None
    live_obj: Any                = None

    def __init__(
        self,
        name:     str,
        lineno:   int,
        ast_info: TypeVarInfo | None = None,
        live_obj: Any                = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.ALIAS, lineno=lineno)
        self.ast_info = ast_info
        self.live_obj = live_obj


@dataclass
class OverloadGroup(StubSymbol):
    """
    Multiple ``@overload`` variants that share a single function name.

    Parameters
    ----------
    variants : list of FunctionSymbol
        One entry per ``@overload``-decorated definition, in source order.
    live_func : callable or None
        The concrete implementation callable (the non-``@overload`` one).

    Examples
    --------
    >>> grp = OverloadGroup(name="parse", lineno=10)
    >>> len(grp.variants)
    0
    """
    variants:  list[FunctionSymbol] = field(default_factory=list)
    live_func: Any | None           = None

    def __init__(
        self,
        name:      str,
        lineno:    int,
        variants:  list[FunctionSymbol] | None = None,
        live_func: Any | None                  = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.OVERLOAD, lineno=lineno)
        self.variants  = variants if variants is not None else []
        self.live_func = live_func


# ---------------------------------------------------------------------------
# Symbol table
# ---------------------------------------------------------------------------

class SymbolTable:
    """
    Ordered collection of :class:`StubSymbol` entries for one module.

    Preserves source-definition order so that the emitted stub mirrors
    the original file layout.  Provides lookup by name and iteration by
    kind.

    Examples
    --------
    >>> tbl = SymbolTable()
    >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
    >>> tbl.add(FunctionSymbol(name="bar", lineno=10))
    >>> len(tbl)
    2
    >>> tbl.get("Foo").kind
    <SymbolKind.CLASS: 'class'>
    >>> "Foo" in tbl
    True
    >>> "Missing" in tbl
    False
    """

    def __init__(self) -> None:
        self._symbols: list[StubSymbol]      = []
        self._index:   dict[str, StubSymbol] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, symbol: StubSymbol) -> None:
        """
        Append *symbol* to the table.

        If a symbol with the same name already exists it is **overwritten**
        in the index (the old entry is retained in the ordered list for
        compatibility, but lookup returns the newer entry).
        """
        self._symbols.append(symbol)
        self._index[symbol.name] = symbol

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> StubSymbol | None:
        """Return the symbol for *name*, or ``None`` if not present."""
        return self._index.get(name)

    def get_class(self, name: str) -> ClassSymbol | None:
        """Return the :class:`ClassSymbol` for *name*, or ``None``."""
        sym = self._index.get(name)
        return sym if isinstance(sym, ClassSymbol) else None

    def get_function(self, name: str) -> FunctionSymbol | None:
        """Return the :class:`FunctionSymbol` for *name*, or ``None``."""
        sym = self._index.get(name)
        return sym if isinstance(sym, FunctionSymbol) else None

    # ------------------------------------------------------------------
    # Iteration by kind
    # ------------------------------------------------------------------

    def by_kind(self, kind: SymbolKind) -> Iterator[StubSymbol]:
        """Yield all symbols of *kind* in definition order."""
        for s in self._symbols:
            if s.kind == kind:
                yield s

    def classes(self) -> Iterator[ClassSymbol]:
        """Yield all :class:`ClassSymbol` entries in source order."""
        for s in self._symbols:
            if isinstance(s, ClassSymbol):
                yield s

    def functions(self) -> Iterator[FunctionSymbol]:
        """Yield all top-level :class:`FunctionSymbol` entries in source order."""
        for s in self._symbols:
            if isinstance(s, FunctionSymbol):
                yield s

    def variables(self) -> Iterator[VariableSymbol]:
        """Yield all :class:`VariableSymbol` entries in source order."""
        for s in self._symbols:
            if isinstance(s, VariableSymbol):
                yield s

    def aliases(self) -> Iterator[AliasSymbol]:
        """Yield all :class:`AliasSymbol` entries in source order."""
        for s in self._symbols:
            if isinstance(s, AliasSymbol):
                yield s

    def overload_groups(self) -> Iterator[OverloadGroup]:
        """Yield all :class:`OverloadGroup` entries in source order."""
        for s in self._symbols:
            if isinstance(s, OverloadGroup):
                yield s

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------

    def all_names(self) -> list[str]:
        """Return all symbol names in definition order."""
        return [s.name for s in self._symbols]

    def sorted_by_line(self) -> list[StubSymbol]:
        """Return all symbols sorted by lineno ascending."""
        return sorted(self._symbols, key=lambda s: s.lineno)

    # ------------------------------------------------------------------
    # Python protocols
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._symbols)

    def __iter__(self) -> Iterator[StubSymbol]:
        return iter(self._symbols)

    def __contains__(self, name: object) -> bool:
        return name in self._index

    def __repr__(self) -> str:
        return (
            f"SymbolTable({len(self._symbols)} symbols: "
            + ", ".join(
                f"{s.kind.value} {s.name!r}" for s in self._symbols[:5]
            )
            + ("..." if len(self._symbols) > 5 else "")
            + ")"
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_symbol_table(
    module:          "_builtin_types.ModuleType | None",
    module_name:     str,
    ast_symbols:     ASTSymbols,
    all_exports:     "set[str] | None" = None,
    include_private: bool               = False,
) -> SymbolTable:
    """
    Build a :class:`SymbolTable` by merging runtime and AST information.

    Live objects from *module* are matched against the
    :class:`~stubpy.ast_pass.ASTSymbols` by name and combined into typed
    :class:`StubSymbol` entries.  When *module* is ``None`` (AST-only mode),
    all ``live_*`` fields are ``None``.

    The symbol table is populated in this order:

    1. **TypeAlias / TypeVar** declarations (from AST).
    2. **Classes** — merged with ``inspect.getmembers`` when *module* is
       available; filtered to symbols whose ``__module__`` matches
       *module_name*.
    3. **Module-level functions** — from AST; ``live_func`` set from module.
    4. **Overload groups** — grouped ``@overload`` functions from AST.
    5. **Module-level variables** — from AST; ``live_value`` set from module.

    Parameters
    ----------
    module : types.ModuleType or None
        Loaded module from :func:`~stubpy.loader.load_module`, or ``None``
        for AST-only mode.
    module_name : str
        Synthetic ``_stubpy_target_*`` module name used to filter local
        classes from imported ones.
    ast_symbols : ASTSymbols
        Output from :func:`~stubpy.ast_pass.ast_harvest`.
    all_exports : set of str or None
        When provided, only names in this set are included.  ``None``
        means include all public (non-underscore-prefixed) names unless
        *include_private* is ``True``.
    include_private : bool
        When ``True``, names starting with ``_`` are **not** filtered out.
        Defaults to ``False``.

    Returns
    -------
    SymbolTable
        Populated, source-order-preserving symbol table.

    Examples
    --------
    >>> import types as _t
    >>> from stubpy.ast_pass import ast_harvest
    >>> m = _t.ModuleType("_stubpy_target_ex")
    >>> class Foo: pass
    >>> Foo.__module__ = "_stubpy_target_ex"
    >>> m.Foo = Foo
    >>> syms = ast_harvest("class Foo: pass")
    >>> tbl = build_symbol_table(m, "_stubpy_target_ex", syms)
    >>> tbl.get("Foo").kind.value
    'class'
    """
    table = SymbolTable()

    # -- Build AST class lookup map for O(1) merging ----------------------
    ast_class_map: dict[str, ClassInfo] = {c.name: c for c in ast_symbols.classes}

    # -- Identify overload groups from AST ---------------------------------
    overload_groups_ast: dict[str, list[FunctionInfo]] = {}
    for fn in ast_symbols.functions:
        if fn.is_overload:
            overload_groups_ast.setdefault(fn.name, []).append(fn)

    def _include(name: str) -> bool:
        """Return True if this name should appear in the stub."""
        if name.startswith("_"):
            # Private names are controlled solely by include_private.
            # __all__ never lists private names, so they must bypass that
            # check entirely — otherwise --include-private has no effect
            # when __all__ is present.
            return include_private
        if all_exports is not None and name not in all_exports:
            return False
        return True

    # ── 1. TypeAlias / TypeVar declarations ──────────────────────────────
    for tv in ast_symbols.typevar_decls:
        if not _include(tv.name):
            continue
        live_obj = getattr(module, tv.name, None) if module is not None else None
        table.add(AliasSymbol(
            name=tv.name,
            lineno=tv.lineno,
            ast_info=tv,
            live_obj=live_obj,
        ))

    # ── 2. Classes ────────────────────────────────────────────────────────
    # Collect (lineno, ClassSymbol) pairs so we can sort before inserting.
    class_entries: list[tuple[int, ClassSymbol]] = []

    if module is not None:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if getattr(obj, "__module__", None) != module_name:
                continue
            if not _include(obj.__name__):
                continue
            # Prefer AST-derived line number for accurate source ordering
            ai = ast_class_map.get(obj.__name__)
            if ai:
                lineno = ai.lineno
            else:
                try:
                    lineno = inspect.getsourcelines(obj)[1]
                except Exception:
                    lineno = 0
            class_entries.append((lineno, ClassSymbol(
                name=obj.__name__,
                lineno=lineno,
                live_type=obj,
                ast_info=ai,
            )))
    else:
        # AST-only mode: no live types available
        for ci in ast_symbols.classes:
            if not _include(ci.name):
                continue
            class_entries.append((ci.lineno, ClassSymbol(
                name=ci.name,
                lineno=ci.lineno,
                live_type=None,
                ast_info=ci,
            )))

    # Insert classes in source order
    for _, sym in sorted(class_entries, key=lambda t: t[0]):
        table.add(sym)

    # ── 3. Module-level functions (non-overloaded) ────────────────────────
    for fi in ast_symbols.functions:
        if not _include(fi.name):
            continue
        if fi.is_overload:
            continue  # collected separately below
        live_func = None
        if module is not None:
            candidate = getattr(module, fi.name, None)
            if callable(candidate):
                live_func = candidate
        table.add(FunctionSymbol(
            name=fi.name,
            lineno=fi.lineno,
            live_func=live_func,
            ast_info=fi,
        ))

    # ── 4. Overload groups ────────────────────────────────────────────────
    for name, variants in overload_groups_ast.items():
        if not _include(name):
            continue
        live_func = None
        if module is not None:
            candidate = getattr(module, name, None)
            if callable(candidate):
                live_func = candidate
        lineno = variants[0].lineno if variants else 0
        group  = OverloadGroup(name=name, lineno=lineno, live_func=live_func)
        for variant_fi in variants:
            group.variants.append(FunctionSymbol(
                name=name,
                lineno=variant_fi.lineno,
                live_func=live_func,
                ast_info=variant_fi,
            ))
        table.add(group)

    # ── 5. Module-level variables ─────────────────────────────────────────
    for vi in ast_symbols.variables:
        if not _include(vi.name):
            continue
        live_value = getattr(module, vi.name, None) if module is not None else None
        # Infer type from runtime value when no annotation is present
        inferred: str | None = None
        if live_value is not None and vi.annotation_str is None:
            inferred = type(live_value).__name__
        table.add(VariableSymbol(
            name=vi.name,
            lineno=vi.lineno,
            live_value=live_value,
            annotation_str=vi.annotation_str,
            inferred_type_str=inferred,
            ast_info=vi,
        ))

    return table
