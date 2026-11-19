"""
The method resolution order of a class, computed from source.
"""
from __future__ import annotations

import builtins
import importlib
import sys

from ._lookup import ClassRef, Resolver

_IGNORED_BASES: frozenset[str] = frozenset({"object", "Generic", "Protocol", "ABC", "typing.Generic",
                                            "typing.Protocol", "abc.ABC"})


class Opaque:
    """A base class the source index cannot see (stdlib, third party); *origin* is its dotted import path."""

    def __init__(self, name: str, origin: str | None = None) -> None:
        self.name = name
        self.origin = origin

    def defines(self, method: str) -> bool:
        """True unless *origin* is a standard-library class known not to define *method*."""
        if self.origin is None or self.origin.split(".")[0] not in sys.stdlib_module_names:
            return True
        module_name, _, attr = self.origin.rpartition(".")
        try:
            cls = getattr(importlib.import_module(module_name), attr)
        except (ImportError, AttributeError):
            return True
        return not isinstance(cls, type) or any(method in vars(k) for k in cls.__mro__[:-1])


def _origin(cref: ClassRef, name: str) -> str | None:
    """Return the dotted path an imported base *name* comes from, as the module's imports say."""
    head, _, rest = name.partition(".")
    for imp in reversed(cref.module.symbols.imports):
        if imp.local != head or (imp.module or "").startswith("."):
            continue
        base = f"{imp.module}.{imp.name}" if imp.module else (imp.name if imp.asname else head)
        return f"{base}.{rest}" if rest else base
    return f"builtins.{name}" if "." not in name and hasattr(builtins, name) else None


def bases_of(resolver: Resolver, cref: ClassRef) -> list[ClassRef | Opaque]:
    """Return the resolved direct bases of *cref*; keyword arguments and typing-only bases are skipped."""
    out: list[ClassRef | Opaque] = []
    for text in cref.info.bases:
        if "=" in text:
            continue
        name = text.split("[")[0].strip()
        if name in _IGNORED_BASES:
            continue
        ref = resolver.dotted(cref.module, name)
        out.append(ref if isinstance(ref, ClassRef) else Opaque(name, _origin(cref, name)))
    return out


def _key(c: ClassRef | Opaque) -> object:
    return c.key if isinstance(c, ClassRef) else ("opaque", c.name)


def static_mro(resolver: Resolver, cref: ClassRef, _seen: frozenset[str] = frozenset()) -> list[ClassRef | Opaque]:
    """Return the C3 linearisation of *cref* (itself first); an inconsistent hierarchy gives a depth-first order."""
    if cref.key in _seen:
        return [cref]
    seen = _seen | {cref.key}
    bases = bases_of(resolver, cref)
    seqs = [static_mro(resolver, b, seen) if isinstance(b, ClassRef) else [b] for b in bases]
    seqs = [list(s) for s in seqs if s] + ([list(bases)] if bases else [])
    out: list[ClassRef | Opaque] = [cref]
    while seqs:
        head = None
        for seq in seqs:
            candidate = seq[0]
            if not any(_key(candidate) in {_key(x) for x in other[1:]} for other in seqs):
                head = candidate
                break
        if head is None:
            rest = [c for seq in seqs for c in seq]
            out += [c for i, c in enumerate(rest) if _key(c) not in {_key(x) for x in rest[:i]} | {_key(o) for o in out}]
            break
        out.append(head)
        seqs = [[c for c in seq if _key(c) != _key(head)] for seq in seqs]
        seqs = [s for s in seqs if s]
    return out
