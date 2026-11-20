"""
The pieces a harvested function is made of: raw parameters, non-literal defaults, local imports and version branches.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


@dataclass(eq=False)
class VersionBlock:
    """An ``if`` / ``elif`` / ``else`` chain whose tests only check ``sys.version_info`` / ``sys.platform``.

    Attributes
    ----------
    lineno : int
        Line of the ``if``.
    tests : list of str or None
        Source of each branch's test; ``None`` for the ``else`` branch.
    taken : int or None
        The branch the running interpreter takes, ``None`` when it takes none.

    Examples
    --------
    >>> VersionBlock(1, ["sys.version_info >= (3, 9)", None], taken=0).taken
    0
    """
    lineno: int
    tests: list[str | None]
    taken: int | None = None


#: The version branches enclosing a definition, outermost first: ``(block, branch index)`` pairs
Branch = tuple


def on_taken_path(branch: Branch) -> bool:
    """Return ``True`` when the running interpreter takes every branch of *branch*.

    Parameters
    ----------
    branch : tuple
        ``(VersionBlock, index)`` pairs enclosing a definition, outermost first.

    Returns
    -------
    bool
        ``True`` for an unconditional definition (an empty tuple).

    Examples
    --------
    >>> block = VersionBlock(1, ["sys.version_info >= (3, 9)", None], taken=0)
    >>> on_taken_path(((block, 0),)), on_taken_path(((block, 1),)), on_taken_path(())
    (True, False, True)
    """
    return all(block.taken == index for block, index in branch)


@dataclass
class RawParam:
    """One parameter of an AST function definition.

    Attributes
    ----------
    name : str
        Parameter name without ``*`` / ``**``.
    kind : str
        An :class:`inspect.Parameter` kind name, e.g. ``"KEYWORD_ONLY"``.
    annotation_str : str or None
        Unparsed annotation.
    inferred_type_str : str or None
        Type inferred from a literal default.
    default_repr : str or None
        Unparsed default expression; ``None`` when required.

    Examples
    --------
    >>> RawParam("x", "POSITIONAL_OR_KEYWORD", annotation_str="int", default_repr="0").default_repr
    '0'
    """
    name: str
    kind: str
    annotation_str: str | None = None
    inferred_type_str: str | None = None
    default_repr: str | None = None


class NonLiteralDefault:
    """A default known only as source text (``MISSING``, ``Unit.PX``), rendered as that text when it is in scope.

    Parameters
    ----------
    source_repr : str
        The default expression as written in the source.

    Examples
    --------
    >>> repr(NonLiteralDefault("Unit.PX"))
    'Unit.PX'
    """
    __slots__ = ("_repr",)

    def __init__(self, source_repr: str) -> None:
        self._repr = source_repr

    def __repr__(self) -> str:
        return self._repr


class ConsumedHints(dict):
    """Empty hints marking a keyword popped from ``**kwargs``; a callee's same-named parameter may type it.

    Examples
    --------
    >>> ConsumedHints()
    {}
    """


class LocalImport(NamedTuple):
    """A name bound by an import statement inside a function body: ``from <.*level><module> import <attr>``.

    Attributes
    ----------
    level : int
        Number of leading dots.
    module : str
        The module without its dots.
    attr : str or None
        The imported attribute; ``None`` for a plain ``import module``.

    Examples
    --------
    >>> LocalImport(1, "sibling", "Thing")
    LocalImport(level=1, module='sibling', attr='Thing')
    """
    level: int
    module: str
    attr: str | None


@dataclass(frozen=True)
class BranchDispatch:
    """``**kwargs`` / ``*args`` forwarded to a different callee per literal value of one parameter.

    Attributes
    ----------
    selector : str
        The parameter compared against literals.
    kind : str
        ``"if"``, ``"match"`` or ``"dict"`` (``{key: Callee}[selector](**kwargs)``).
    cases : tuple
        ``(literals, callees, returned)`` per branch: the literal sources, the callees
        forwarded to, and whether the branch returns the single callee's result.
    callees : frozenset of str
        Every callee forwarded to inside the dispatch, ``else`` arms included.
    table : str or None
        The module-level dict a ``"dict"`` dispatch indexes; its cases are read at emit time.
    forwards_kwargs, forwards_args : bool
        What a ``"dict"`` dispatch call passes on.
    positional : int
        Positional arguments a ``"dict"`` dispatch call binds before the variadics.
    explicit : frozenset of str
        Keywords a ``"dict"`` dispatch call passes by name.
    returned : bool
        A ``"dict"`` dispatch call is returned directly.

    Examples
    --------
    >>> BranchDispatch("kind", "if", ((("'a'",), ("A",), True),), frozenset({"A"})).selector
    'kind'
    """
    selector: str
    kind: str
    cases: tuple[tuple[tuple[str, ...], tuple[str, ...], bool], ...] = ()
    callees: frozenset[str] = frozenset()
    table: str | None = None
    forwards_kwargs: bool = True
    forwards_args: bool = False
    positional: int = 0
    explicit: frozenset[str] = frozenset()
    returned: bool = False
