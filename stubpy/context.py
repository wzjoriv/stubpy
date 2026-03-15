"""
stubpy.context
==============

Run-scoped mutable state for a single stub-generation pass.

Every call to :func:`~stubpy.generator.generate_stub` creates a fresh
:class:`StubContext`. Keeping state in a dataclass rather than
module-level globals makes the generator fully re-entrant and each
unit test independently isolated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple


class AliasEntry(NamedTuple):
    """A pairing of a live annotation object with its stub alias string.

    Created by :func:`~stubpy.aliases.build_alias_registry` and stored
    in :attr:`StubContext.alias_registry`.

    Parameters
    ----------
    annotation : Any
        The live Python object representing the type alias — for example,
        the result of evaluating ``str | float | int`` at import time.
    alias_str : str
        The stub-safe dotted name to emit in place of the raw type —
        for example ``"types.Length"``.

    Examples
    --------
    >>> entry = AliasEntry(annotation=str | float | int, alias_str="types.Length")
    >>> entry.alias_str
    'types.Length'
    >>> entry.annotation == (str | float | int)
    True
    """

    annotation: Any
    alias_str: str


@dataclass
class StubContext:
    """Mutable state container scoped to one stub-generation run.

    Create one instance per :func:`~stubpy.generator.generate_stub` call;
    never share instances across concurrent calls. All fields start empty
    and are populated progressively through the pipeline:

    1. :func:`~stubpy.aliases.build_alias_registry` fills
       :attr:`alias_registry` and :attr:`type_module_imports`.
    2. :meth:`lookup_alias` populates :attr:`used_type_imports` lazily
       as annotations are converted.
    3. :func:`~stubpy.generator.generate_stub` reads
       :attr:`used_type_imports` when assembling the ``.pyi`` header.

    Parameters
    ----------
    alias_registry : list of AliasEntry
        All ``(annotation, alias_str)`` pairs discovered by scanning
        imported type sub-modules. Populated once at the start of a run.
    type_module_imports : dict
        Maps ``module_alias -> import_statement`` for every type-alias
        sub-module found in the source file.
        Example: ``{"types": "from demo import types"}``.
    used_type_imports : dict
        Subset of :attr:`type_module_imports` for aliases that were
        actually referenced during stub body generation. Only these
        entries appear in the final ``.pyi`` header.

    Examples
    --------
    >>> from stubpy.context import StubContext, AliasEntry
    >>> ctx = StubContext()
    >>> ctx.alias_registry.append(AliasEntry(str | int, "types.MyAlias"))
    >>> ctx.type_module_imports["types"] = "from mypkg import types"
    >>> ctx.lookup_alias(str | int)
    'types.MyAlias'
    >>> ctx.used_type_imports
    {'types': 'from mypkg import types'}
    """

    alias_registry: list[AliasEntry] = field(default_factory=list)
    type_module_imports: dict[str, str] = field(default_factory=dict)
    used_type_imports: dict[str, str] = field(default_factory=dict)

    def lookup_alias(self, annotation: Any) -> str | None:
        """Return the alias string for *annotation* if registered, else ``None``.

        Iterates :attr:`alias_registry` comparing each entry's annotation
        to *annotation* using ``==``. On a match the entry's module alias
        is added to :attr:`used_type_imports` so its import statement will
        appear in the generated ``.pyi`` header.

        Parameters
        ----------
        annotation : Any
            Any live Python annotation object — a class, a PEP 604 union,
            a subscripted typing generic, etc.

        Returns
        -------
        str or None
            The registered alias string (e.g. ``"types.Length"``) on a
            match, or ``None`` if no alias matches.

        Notes
        -----
        Equality comparison (``==``) is used rather than identity (``is``)
        because PEP 604 unions and typing generics with the same structure
        compare equal even when created independently. Objects that raise
        on ``==`` (e.g. NumPy arrays) are silently skipped.

        Examples
        --------
        >>> ctx = StubContext()
        >>> ctx.alias_registry.append(AliasEntry(str | int, "types.T"))
        >>> ctx.type_module_imports["types"] = "from pkg import types"
        >>> ctx.lookup_alias(str | int)
        'types.T'
        >>> ctx.lookup_alias(str | float) is None
        True
        """
        for entry in self.alias_registry:
            try:
                if entry.annotation == annotation:
                    module_alias = entry.alias_str.split(".")[0]
                    if module_alias in self.type_module_imports:
                        self.used_type_imports[module_alias] = (
                            self.type_module_imports[module_alias]
                        )
                    return entry.alias_str
            except Exception:
                pass
        return None
