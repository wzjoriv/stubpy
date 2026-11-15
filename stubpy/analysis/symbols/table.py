"""The :class:`SymbolTable`: an ordered, name-indexed collection of symbols."""
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
        self._hidden: dict[str, StubSymbol] = {}
        self._function_infos: dict | None = None

    def add(self, symbol: StubSymbol) -> None:
        """Append *symbol*; a later symbol with the same name wins lookups."""
        self._symbols.append(symbol)
        self._index[symbol.name] = symbol
        self._function_infos = None

    def add_hidden(self, symbol: StubSymbol) -> None:
        """Keep *symbol* out of the stub unless :meth:`promote` brings it in (private or outside ``__all__``)."""
        self._hidden.setdefault(symbol.name, symbol)

    def hidden_names(self) -> set[str]:
        """Return the names of the symbols held back from the stub."""
        return set(self._hidden)

    def promote(self, name: str) -> StubSymbol | None:
        """Move the hidden symbol *name* into the table and return it; ``None`` when there is none."""
        symbol = self._hidden.pop(name, None)
        if symbol is not None:
            self.add(symbol)
        return symbol

    def function_infos(self) -> dict:
        """Map each function name to its AST :class:`FunctionInfo`, computed once per table state."""
        if self._function_infos is None:
            self._function_infos = {
                s.name: s.ast_info for s in self._symbols
                if isinstance(s, FunctionSymbol) and s.ast_info is not None
            }
        return self._function_infos

    def get(self, name: str) -> StubSymbol | None:
        """Return the symbol named *name*, or ``None``."""
        return self._index.get(name)

    def get_class(self, name: str) -> ClassSymbol | None:
        """Return the :class:`ClassSymbol` named *name*, hidden or not, or ``None``."""
        sym = self._index.get(name) or self._hidden.get(name)
        return sym if isinstance(sym, ClassSymbol) else None

    def get_function(self, name: str) -> FunctionSymbol | None:
        """Return the :class:`FunctionSymbol` named *name*, or ``None``."""
        sym = self._index.get(name)
        return sym if isinstance(sym, FunctionSymbol) else None

    def by_kind(self, kind: SymbolKind) -> Iterator[StubSymbol]:
        """Yield the symbols of *kind* in definition order."""
        for s in self._symbols:
            if s.kind == kind:
                yield s

    def classes(self) -> Iterator[ClassSymbol]:
        """Yield the class symbols in definition order."""
        for s in self._symbols:
            if isinstance(s, ClassSymbol):
                yield s

    def functions(self) -> Iterator[FunctionSymbol]:
        """Yield the function symbols in definition order."""
        for s in self._symbols:
            if isinstance(s, FunctionSymbol):
                yield s

    def variables(self) -> Iterator[VariableSymbol]:
        """Yield the variable symbols in definition order."""
        for s in self._symbols:
            if isinstance(s, VariableSymbol):
                yield s

    def aliases(self) -> Iterator[AliasSymbol]:
        """Yield the alias symbols in definition order."""
        for s in self._symbols:
            if isinstance(s, AliasSymbol):
                yield s

    def overload_groups(self) -> Iterator[OverloadGroup]:
        """Yield the overload groups in definition order."""
        for s in self._symbols:
            if isinstance(s, OverloadGroup):
                yield s

    def all_names(self) -> list[str]:
        """Return all symbol names in definition order."""
        return [s.name for s in self._symbols]

    def sorted_by_line(self) -> list[StubSymbol]:
        """Return all symbols sorted by source line."""
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
