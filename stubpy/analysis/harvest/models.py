"""
Data containers for metadata harvested from a source file's AST.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class FunctionInfo:
    """Metadata for one function or method definition.

    Hint decorators are not listed in *decorators*.

    Attributes
    ----------
    name, lineno : str, int
        Definition name and source line.
    is_async : bool
        ``True`` for an ``async def`` coroutine (a stub writes it as ``async def``).
    is_async_generator : bool
        ``True`` for an ``async def`` that yields (a stub writes it as a
        plain ``def`` returning an async iterator).
    decorators : list of str
        Decorator source text, e.g. ``["classmethod", "functools.lru_cache(maxsize=8)"]``.
    is_overload : bool
        ``True`` when decorated with ``@overload``.
    raw_arg_annotations : dict
        Parameter name to unparsed annotation; variadics are keyed
        ``"*args"`` / ``"**kwargs"``.
    raw_arg_inferred_types : dict
        Parameter name to type inferred from its literal default, for
        unannotated parameters only.
    raw_inferred_return : str or None
        Return type inferred from literal ``return`` statements.
    structural_return : str or None
        Return type implied by the body's shape: ``Iterator[T]`` /
        ``Generator[T, S, R]`` / ``AsyncIterator[T]`` for generators yielding
        literals, ``NoReturn`` when the body always raises.
    raw_params : list of RawParam
        All parameters in declaration order.
    raw_return_annotation : str or None
        Unparsed return annotation.
    kwargs_forwarded_to, args_forwarded_to : list of str
        Callables that receive ``**kwargs`` / ``*args`` in the body.
    kwargs_positional_skips : dict of str to int
        Positional arguments pre-bound at each ``**kwargs`` call site.
    kwargs_explicit_names : dict of str to set of str
        Keyword arguments passed by name at each ``**kwargs`` call site.
    kwargs_method_targets, args_method_targets : list of str
        Methods called as ``self.X(...)`` / ``cls.X(...)`` with the variadic.
    kwargs_unknown_starred : set of str
        Targets also called with a ``*x`` that is not the function's own ``*args``.
    kwargs_consumed : dict of str to str or None
        Keys popped or deleted from ``**kwargs``, with the ``pop`` default
        source (``None`` when the key is required).
    kwargs_injected : set of str
        Keys the body assigns into ``**kwargs`` itself.
    kwargs_dynamic : bool
        ``**kwargs`` reaches a callee that cannot be named statically.
    kwargs_read : dict of str to str or None
        Keys read but not removed (``kwargs["k"]``, ``kwargs.get("k", d)``), with the default
        source (``None`` when the key is required).
    args_read : int
        One past the highest ``args[i]`` index the body reads; ``0`` when none.
    dispatch : BranchDispatch or None
        Forwarding that picks its callee from a literal-compared parameter.
    selected : tuple of (str, str) or None
        ``(selector, annotation)`` of one dispatch branch; set on the variants built for ``@overload``.
    local_imports : dict of str to LocalImport
        Names bound by imports inside the body.
    is_stub_body : bool
        The body is only a docstring, ``pass``, ``...`` or ``raise NotImplementedError``.
    hint_signature, hint_returns : str or None
        Text of a ``@hint.signature(...)`` / ``@hint.returns(...)`` decorator.
    hint_ignore : bool
        Decorated with ``@hint.ignore``.
    type_params : list of str
        PEP 695 parameters (``def f[T](...)``).
    docstring : str or None
        Body docstring for ``include_docstrings`` stubs; set for compiled callables.
    branch : tuple
        The version branches enclosing the definition; ``()`` when unconditional.

    Examples
    --------
    >>> info = FunctionInfo(name="load", lineno=4, is_async=True)
    >>> info.name, info.is_async, info.raw_params
    ('load', True, [])
    """
    name: str
    lineno: int
    is_async: bool = False
    is_async_generator: bool = False
    decorators: list[str] = field(default_factory=list)
    is_overload: bool = False
    raw_arg_annotations: dict[str, str] = field(default_factory=dict)
    raw_arg_inferred_types: dict[str, str] = field(default_factory=dict)
    raw_inferred_return: str | None = None
    structural_return: str | None = None
    raw_params: list[RawParam] = field(default_factory=list)
    raw_return_annotation: str | None = None
    kwargs_forwarded_to: list[str] = field(default_factory=list)
    args_forwarded_to: list[str] = field(default_factory=list)
    kwargs_positional_skips: dict[str, int] = field(default_factory=dict)
    kwargs_explicit_names: dict[str, set[str]] = field(default_factory=dict)
    kwargs_method_targets: list[str] = field(default_factory=list)
    args_method_targets: list[str] = field(default_factory=list)
    kwargs_unknown_starred: set[str] = field(default_factory=set)
    kwargs_consumed: dict[str, str | None] = field(default_factory=dict)
    kwargs_injected: set[str] = field(default_factory=set)
    kwargs_dynamic: bool = False
    kwargs_read: dict[str, str | None] = field(default_factory=dict)
    args_read: int = 0
    dispatch: BranchDispatch | None = None
    selected: tuple[str, str] | None = None
    local_imports: dict[str, LocalImport] = field(default_factory=dict)
    is_stub_body: bool = False
    hint_signature: str | None = None
    hint_returns: str | None = None
    hint_ignore: bool = False
    type_params: list[str] = field(default_factory=list)
    docstring: str | None = None
    branch: Branch = ()


@dataclass
class ClassInfo:
    """Metadata for one class definition: bases, decorators, methods, attributes, nested classes and ``@hint.ignore``.

    Attributes
    ----------
    name, lineno : str, int
        Class name and source line.
    bases : list of str
        Unparsed base-class expressions.
    decorators : list of str
        Decorator source text.
    methods : list of FunctionInfo
        Methods defined in the class body.
    attributes : list of VariableInfo
        Class-level variables.
    classes : list of ClassInfo
        Nested classes.
    hint_ignore : bool
        Decorated with ``@hint.ignore``.
    type_params : list of str
        PEP 695 parameters (``class C[T]``).
    docstring : str or None
        Set for compiled classes and used by ``include_docstrings`` stubs.
    branch : tuple
        The version branches enclosing the definition; ``()`` when unconditional.
    instance_attributes : list of VariableInfo
        Typed ``self.x`` assignments in the methods.
    slots : list of str
        The literal ``__slots__`` names.

    Examples
    --------
    >>> ClassInfo(name="Widget", lineno=1, bases=["Base"]).bases
    ['Base']
    """
    name: str
    lineno: int
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    attributes: list[VariableInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    hint_ignore: bool = False
    type_params: list[str] = field(default_factory=list)
    docstring: str | None = None
    branch: Branch = ()
    instance_attributes: list[VariableInfo] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """One imported name: ``from <module> import <name> as <asname>`` or ``import <name>``.

    Attributes
    ----------
    module : str or None
        Source module with its leading dots; ``None`` for a plain ``import``.
    name : str
        The imported name or module.
    asname : str or None
        The ``as`` alias, if any.
    lineno : int
        Source line.
    branch : tuple
        The version branches enclosing the import; ``()`` when unconditional.

    Examples
    --------
    >>> ImportInfo(".sibling", "Thing", "T").local
    'T'
    """
    module: str | None
    name: str
    asname: str | None = None
    lineno: int = 0
    branch: Branch = ()

    @property
    def local(self) -> str:
        """The name the import binds in the module.

        Returns
        -------
        str
            The alias, the imported name, or the first component of a dotted plain import.

        Examples
        --------
        >>> ImportInfo(None, "os.path").local
        'os'
        >>> ImportInfo("pkg", "Thing").local
        'Thing'
        """
        if self.asname:
            return self.asname
        return self.name if self.module is not None else self.name.split(".")[0]


@dataclass
class VariableInfo:
    """Metadata for one module-level assignment, annotated or not.

    Attributes
    ----------
    name, lineno : str, int
        Variable name and source line.
    annotation_str : str or None
        Unparsed annotation.
    value_repr : str or None
        Unparsed assigned value.
    inferred_type_str : str or None
        Type inferred from a literal value.
    branch : tuple
        The version branches enclosing the assignment; ``()`` when unconditional.

    Examples
    --------
    >>> VariableInfo(name="MAX", lineno=1, annotation_str="int", value_repr="10").annotation_str
    'int'
    """
    name: str
    lineno: int
    annotation_str: str | None = None
    value_repr: str | None = None
    inferred_type_str: str | None = None
    branch: Branch = ()


@dataclass
class TypeVarInfo:
    """A ``TypeVar``, ``ParamSpec``, ``TypeVarTuple``, ``TypeAlias`` or ``NewType`` declaration.

    Attributes
    ----------
    name, lineno : str, int
        Declared name and source line.
    kind : str
        The construct, e.g. ``"TypeVar"`` or ``"TypeAlias"``.
    source_str : str
        The unparsed right-hand side.
    type_params : list of str
        PEP 695 parameters of ``type Name[T] = ...``.
    branch : tuple
        The version branches enclosing the declaration; ``()`` when unconditional.

    Examples
    --------
    >>> TypeVarInfo(name="T", lineno=3, kind="TypeVar", source_str="TypeVar('T')").kind
    'TypeVar'
    """
    name: str
    lineno: int
    kind: str
    source_str: str
    type_params: list[str] = field(default_factory=list)
    branch: Branch = ()


@dataclass
class ASTSymbols:
    """Everything :func:`~stubpy.analysis.harvest.ast_harvest` collects from one source file.

    Every definition carries ``branch``: the version blocks
    (:class:`VersionBlock`) it sits in when they are harvested with
    ``version_branches=True``, else ``()``.

    Attributes
    ----------
    classes : list of ClassInfo
        Top-level classes, in source order.
    functions : list of FunctionInfo
        Top-level functions, in source order.
    variables : list of VariableInfo
        Top-level variable assignments.
    typevar_decls : list of TypeVarInfo
        TypeVar / ParamSpec / TypeVarTuple / TypeAlias / NewType declarations.
    all_exports : list of str or None
        String entries of ``__all__``, or ``None`` when absent or not a literal list.
    all_spliced : list of str
        Names spliced into ``__all__`` with ``*name`` (usually another
        module's ``__all__`` imported under that name); ``all_exports`` is
        then incomplete on its own.
    imports : list of ImportInfo
        Top-level imports, in source order.
    skip_file : bool
        ``True`` when the file starts with a ``# stubpy: ignore`` directive.

    Examples
    --------
    >>> symbols = ASTSymbols()
    >>> symbols.classes, symbols.all_exports, symbols.skip_file
    ([], None, False)
    """
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    variables: list[VariableInfo] = field(default_factory=list)
    typevar_decls: list[TypeVarInfo] = field(default_factory=list)
    all_exports: list[str] | None = None
    all_spliced: list[str] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    skip_file: bool = False
