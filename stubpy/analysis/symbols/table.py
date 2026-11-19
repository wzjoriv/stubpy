"""
The :class:`SymbolTable`: an ordered, name-indexed collection of symbols.
"""
from __future__ import annotations

from collections.abc import Iterator

from .models import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    StubSymbol,
    SymbolKind,
    VariableSymbol,
)


class SymbolTable:
    """Ordered collection of the symbols of one module.

    Keeps definition order and supports lookup by name and iteration by kind.

    Examples
    --------
    >>> tbl = SymbolTable()
    >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
    >>> tbl.add(FunctionSymbol(name="bar", lineno=10))
    >>> len(tbl), "Foo" in tbl, tbl.get("Missing") is None
    (2, True, True)
    """

    def __init__(self) -> None:
        self._symbols: list[StubSymbol] = []
        self._index: dict[str, StubSymbol] = {}
        self._hidden: dict[str, list[StubSymbol]] = {}
        self._function_infos: dict | None = None

    def add(self, symbol: StubSymbol) -> None:
        """Append *symbol*; a later symbol with the same name wins lookups, unless it is dormant and the earlier is not.

        Parameters
        ----------
        symbol : StubSymbol
            The symbol to add.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
        >>> tbl.all_names()
        ['Foo']
        """
        self._symbols.append(symbol)
        current = self._index.get(symbol.name)
        if current is None or not symbol.dormant or current.dormant:
            self._index[symbol.name] = symbol
        self._function_infos = None

    def discard(self, name: str) -> None:
        """Remove every symbol named *name*, hidden or not.

        Parameters
        ----------
        name : str
            Name of the symbols to drop.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
        >>> tbl.discard("Foo")
        >>> len(tbl)
        0
        """
        self._symbols = [s for s in self._symbols if s.name != name]
        self._index.pop(name, None)
        self._hidden.pop(name, None)
        self._function_infos = None

    def add_hidden(self, symbol: StubSymbol) -> None:
        """Keep *symbol* out of the stub unless :meth:`promote` brings it in (private or outside ``__all__``).

        Parameters
        ----------
        symbol : StubSymbol
            The symbol to hold back.

        See Also
        --------
        promote : Move a hidden symbol into the table.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add_hidden(ClassSymbol(name="_Base", lineno=1))
        >>> len(tbl), tbl.hidden_names()
        (0, {'_Base'})
        """
        self._hidden.setdefault(symbol.name, []).append(symbol)

    def hidden_names(self) -> set[str]:
        """Return the names of the symbols held back from the stub.

        Returns
        -------
        set of str
            Names added with :meth:`add_hidden` and not yet promoted.

        Examples
        --------
        >>> SymbolTable().hidden_names()
        set()
        """
        return set(self._hidden)

    def promote(self, name: str) -> list[StubSymbol]:
        """Move the hidden symbols named *name* (one per version branch) into the table and return them.

        Parameters
        ----------
        name : str
            Name of the hidden symbols.

        Returns
        -------
        list of StubSymbol
            The promoted symbols; empty when none are hidden under *name*.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add_hidden(ClassSymbol(name="_Base", lineno=1))
        >>> [s.name for s in tbl.promote("_Base")], len(tbl)
        (['_Base'], 1)
        """
        symbols = self._hidden.pop(name, [])
        for symbol in symbols:
            self.add(symbol)
        return symbols

    def function_infos(self) -> dict:
        """Map each function name to its AST :class:`FunctionInfo`, computed once per table state.

        Returns
        -------
        dict
            Function name to ``FunctionInfo``, for the functions that have AST metadata.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(FunctionSymbol(name="bar", lineno=1))
        >>> tbl.function_infos()
        {}
        """
        if self._function_infos is None:
            self._function_infos = {
                s.name: s.ast_info for s in self._symbols
                if isinstance(s, FunctionSymbol) and s.ast_info is not None and self._index.get(s.name) is s
            }
        return self._function_infos

    def get(self, name: str) -> StubSymbol | None:
        """Return the symbol named *name*, or ``None``.

        Parameters
        ----------
        name : str
            The symbol name.

        Returns
        -------
        StubSymbol or None
            The visible symbol; hidden symbols are not returned.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
        >>> tbl.get("Foo").name, tbl.get("Bar")
        ('Foo', None)
        """
        return self._index.get(name)

    def get_class(self, name: str) -> ClassSymbol | None:
        """Return the :class:`ClassSymbol` named *name*, hidden or not, or ``None``.

        Parameters
        ----------
        name : str
            The class name.

        Returns
        -------
        ClassSymbol or None
            The class symbol, or ``None`` when *name* is missing or not a class.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add_hidden(ClassSymbol(name="_Base", lineno=1))
        >>> tbl.get_class("_Base").name
        '_Base'
        """
        sym = self._index.get(name)
        if sym is None:
            hidden = self._hidden.get(name, [])
            sym = next((s for s in hidden if not s.dormant), hidden[0] if hidden else None)
        return sym if isinstance(sym, ClassSymbol) else None

    def get_function(self, name: str) -> FunctionSymbol | None:
        """Return the :class:`FunctionSymbol` named *name*, or ``None``.

        Parameters
        ----------
        name : str
            The function name.

        Returns
        -------
        FunctionSymbol or None
            The function symbol, or ``None`` when *name* is missing or not a function.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(FunctionSymbol(name="bar", lineno=1))
        >>> tbl.get_function("bar").name, tbl.get_function("Foo")
        ('bar', None)
        """
        sym = self._index.get(name)
        return sym if isinstance(sym, FunctionSymbol) else None

    def by_kind(self, kind: SymbolKind) -> Iterator[StubSymbol]:
        """Yield the symbols of *kind* in definition order.

        Parameters
        ----------
        kind : SymbolKind
            The category to select.

        Yields
        ------
        StubSymbol
            Each matching symbol.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
        >>> [s.name for s in tbl.by_kind(SymbolKind.CLASS)]
        ['Foo']
        """
        for s in self._symbols:
            if s.kind == kind:
                yield s

    def classes(self) -> Iterator[ClassSymbol]:
        """Yield the class symbols in definition order.

        Yields
        ------
        ClassSymbol
            Each class symbol.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
        >>> [s.name for s in tbl.classes()]
        ['Foo']
        """
        for s in self._symbols:
            if isinstance(s, ClassSymbol):
                yield s

    def functions(self) -> Iterator[FunctionSymbol]:
        """Yield the function symbols in definition order.

        Yields
        ------
        FunctionSymbol
            Each function symbol.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(FunctionSymbol(name="bar", lineno=1))
        >>> [s.name for s in tbl.functions()]
        ['bar']
        """
        for s in self._symbols:
            if isinstance(s, FunctionSymbol):
                yield s

    def variables(self) -> Iterator[VariableSymbol]:
        """Yield the variable symbols in definition order.

        Yields
        ------
        VariableSymbol
            Each variable symbol.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(VariableSymbol(name="MAX", lineno=1))
        >>> [s.name for s in tbl.variables()]
        ['MAX']
        """
        for s in self._symbols:
            if isinstance(s, VariableSymbol):
                yield s

    def aliases(self) -> Iterator[AliasSymbol]:
        """Yield the alias symbols in definition order.

        Yields
        ------
        AliasSymbol
            Each alias symbol.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(AliasSymbol(name="T", lineno=1))
        >>> [s.name for s in tbl.aliases()]
        ['T']
        """
        for s in self._symbols:
            if isinstance(s, AliasSymbol):
                yield s

    def overload_groups(self) -> Iterator[OverloadGroup]:
        """Yield the overload groups in definition order.

        Yields
        ------
        OverloadGroup
            Each overload group.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(OverloadGroup(name="parse", lineno=1))
        >>> [s.name for s in tbl.overload_groups()]
        ['parse']
        """
        for s in self._symbols:
            if isinstance(s, OverloadGroup):
                yield s

    def all_names(self) -> list[str]:
        """Return all symbol names in definition order.

        Returns
        -------
        list of str
            The names of the visible symbols, in the order they were added.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
        >>> tbl.all_names()
        ['Foo']
        """
        return [s.name for s in self._symbols]

    def sorted_by_line(self) -> list[StubSymbol]:
        """Return all symbols sorted by source line.

        Returns
        -------
        list of StubSymbol
            The visible symbols, lowest line first.

        Examples
        --------
        >>> tbl = SymbolTable()
        >>> tbl.add(FunctionSymbol(name="bar", lineno=10))
        >>> tbl.add(ClassSymbol(name="Foo", lineno=1))
        >>> [s.name for s in tbl.sorted_by_line()]
        ['Foo', 'bar']
        """
        return sorted(self._symbols, key=lambda s: s.lineno)

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
