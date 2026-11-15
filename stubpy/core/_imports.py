"""Import statements as bound names: parse, deduplicate by priority, merge per module and render.

Plain ``import x`` lines come first, then
one ``from m import ...`` line per module: standard library, other
absolute modules, relative modules.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass

from stubpy._constants import IMPORT_LINE_LIMIT, TYPING_SINCE


@dataclass(frozen=True)
class ImportEntry:
    """One bound name: ``from module import name as asname``, or ``import name as asname`` (*module* ``None``)."""
    module: str | None
    name: str
    asname: str | None = None

    @property
    def bound(self) -> str:
        """The key used to deduplicate: the bound name, or the full dotted name of an unaliased ``import a.b``."""
        if self.asname:
            return self.asname
        return self.name


def parse_entries(stmt: str) -> list[ImportEntry]:
    """Return the entries of one import statement; ``[]`` when it is not one."""
    try:
        tree = ast.parse(stmt.strip())
    except SyntaxError:
        return []
    out: list[ImportEntry] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            out.extend(ImportEntry(module, a.name, a.asname) for a in node.names)
        elif isinstance(node, ast.Import):
            out.extend(ImportEntry(None, a.name, a.asname) for a in node.names)
    return out


class ImportSet:
    """Imports keyed by bound name; the first entry added for a name wins, so add in priority order."""

    def __init__(self) -> None:
        self._entries: dict[str, ImportEntry] = {}
        self._stars: list[str] = []

    def add(self, stmt: str) -> None:
        """Add every entry of *stmt* whose bound name is still free."""
        for entry in parse_entries(stmt):
            if entry.module == "__future__":
                continue
            if entry.name == "*":
                if entry.module not in self._stars:
                    self._stars.append(entry.module or "")
                continue
            self._entries.setdefault(entry.bound, entry)

    def add_names(self, module: str, names: list[str] | set[str]) -> None:
        """Add ``from module import name`` for each of *names*."""
        for name in names:
            self._entries.setdefault(name, ImportEntry(module, name))

    def retarget(self, version: tuple[int, int]) -> None:
        """Import names ``typing`` gained after *version* from ``typing_extensions``, the others from ``typing``."""
        for key, e in list(self._entries.items()):
            since = TYPING_SINCE.get(e.name)
            if since is None or e.module not in ("typing", "typing_extensions", "warnings"):
                continue
            if e.module == "warnings" and e.name != "deprecated":
                continue
            home = "warnings" if e.name == "deprecated" else "typing"
            self._entries[key] = ImportEntry(home if since <= version else "typing_extensions", e.name, e.asname)

    def bound(self) -> set[str]:
        """Return the names bound so far."""
        return {e.asname or e.name.split(".")[0] for e in self._entries.values()}

    def lines(self) -> list[str]:
        """Return the plain imports, then one sorted line per module in the module order above."""
        plain = sorted({_plain(e) for e in self._entries.values() if e.module is None}, key=_plain_key)
        grouped: dict[str, set[str]] = {}
        for e in self._entries.values():
            if e.module is not None:
                grouped.setdefault(e.module, set()).add(f"{e.name} as {e.asname}" if e.asname else e.name)
        for module in self._stars:
            grouped.setdefault(module, set())
        lines = plain
        for module in sorted(grouped, key=_module_key):
            if module in self._stars:
                lines.append(f"from {module} import *")
            if grouped[module]:
                lines.append(_from_line(module, sorted(grouped[module], key=_name_key)))
        return lines


def _module_key(module: str) -> tuple[int, str]:
    """Order modules as the standard library, then other absolute modules, then relative ones."""
    if module.startswith("."):
        return 2, module
    return (0 if module.split(".")[0] in sys.stdlib_module_names else 1), module


def _plain_key(line: str) -> tuple[int, str]:
    return _module_key(line.split()[1])


def _plain(e: ImportEntry) -> str:
    return f"import {e.name} as {e.asname}" if e.asname else f"import {e.name}"


def _name_key(item: str) -> tuple[int, str]:
    """Order names as isort's order-by-type does: CONSTANTS, then Classes, then everything else."""
    name = item.split(" ")[0]
    if name.isupper() and len(name) > 1:
        return 0, item
    return (1 if name[:1].isupper() else 2), item


def _from_line(module: str, names: list[str]) -> str:
    """Render ``from module import a, b``, wrapped in parentheses when longer than the line limit."""
    line = f"from {module} import {', '.join(names)}"
    if len(line) <= IMPORT_LINE_LIMIT:
        return line
    inner = "".join(f"    {n},\n" for n in names)
    return f"from {module} import (\n{inner})"
