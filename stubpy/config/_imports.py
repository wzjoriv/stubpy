"""
The import policy: which modules stubpy may import (execute) while it stubs a target.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_KEYWORDS = ("all", "none", "stdlib")


def coerce_imports(value: Any) -> str | tuple[str, ...]:
    """Return ``"all"`` / ``"none"`` / ``"stdlib"`` or a tuple of module patterns; raise on anything else."""
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _KEYWORDS:
            return text
        raise ValueError(f"Invalid imports: {value!r}; expected one of 'all', 'none', 'stdlib' or a list of modules")
    if isinstance(value, Iterable):
        items = tuple(value)
        if all(isinstance(i, str) and _valid(i) for i in items):
            return items
    raise TypeError("imports must be 'all', 'none', 'stdlib' or a list of dotted module names (pkg or pkg.*)")


def coerce_patterns(value: Any, option: str) -> tuple[str, ...]:
    """Return a tuple of dotted module patterns."""
    items = (value,) if isinstance(value, str) else tuple(value) if isinstance(value, Iterable) else None
    if items is None or not all(isinstance(i, str) and _valid(i) for i in items):
        raise TypeError(f"{option} must be a list of dotted module names (pkg or pkg.*)")
    return items


def _valid(pattern: str) -> bool:
    base = pattern[:-2] if pattern.endswith(".*") else pattern
    return bool(base) and all(part.isidentifier() for part in base.split("."))


def _matches(name: str, pattern: str) -> bool:
    """``pkg`` covers ``pkg`` and its submodules; ``pkg.*`` covers the same."""
    base = pattern[:-2] if pattern.endswith(".*") else pattern
    return name == base or name.startswith(base + ".")


def is_stdlib(name: str) -> bool:
    """True for a standard-library or built-in module, or a submodule of one."""
    top = name.partition(".")[0]
    return top in sys.stdlib_module_names or top in sys.builtin_module_names


@dataclass(frozen=True)
class ImportPolicy:
    """*imports* (``"all"``, ``"none"``, ``"stdlib"`` or allowed patterns plus the stdlib) minus *deny*.

    Examples
    --------
    >>> policy = ImportPolicy(("mypkg",), ("mypkg.gui.*",))
    >>> policy.allows("json"), policy.allows("mypkg.core"), policy.allows("mypkg.gui.qt"), policy.allows("numpy")
    (True, True, False, False)
    """
    imports: str | tuple[str, ...] = "all"
    deny: tuple[str, ...] = ()

    @property
    def unrestricted(self) -> bool:
        """True when every import is allowed, so no guard is needed."""
        return self.imports == "all" and not self.deny

    def allows(self, name: str) -> bool:
        """True when the policy lets stubpy import module *name*."""
        if any(_matches(name, p) for p in self.deny):
            return False
        if self.imports == "all":
            return True
        if self.imports == "none":
            return False
        if is_stdlib(name):
            return True
        if self.imports == "stdlib":
            return False
        return any(_matches(name, p) or p.startswith(name + ".") for p in self.imports)
