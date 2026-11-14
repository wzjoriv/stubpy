"""Data containers for metadata harvested from a source file's AST."""
from __future__ import annotations

from dataclasses import dataclass, field


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
    """
    name: str
    kind: str
    annotation_str: str | None = None
    inferred_type_str: str | None = None
    default_repr: str | None = None


@dataclass
class FunctionInfo:
    """Metadata for one function or method definition.

    Attributes
    ----------
    name, lineno : str, int
        Definition name and source line.
    is_async : bool
        ``True`` for ``async def``.
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
    is_stub_body : bool
        The body is only a docstring, ``pass``, ``...`` or ``raise NotImplementedError``.
    hint_signature, hint_returns : str or None
        Text of a ``@hint.signature(...)`` / ``@hint.returns(...)`` decorator.
    hint_ignore : bool
        Decorated with ``@hint.ignore``.

    Hint decorators are not listed in *decorators*.
    """
    name: str
    lineno: int
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    is_overload: bool = False
    raw_arg_annotations: dict[str, str] = field(default_factory=dict)
    raw_arg_inferred_types: dict[str, str] = field(default_factory=dict)
    raw_inferred_return: str | None = None
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
    is_stub_body: bool = False
    hint_signature: str | None = None
    hint_returns: str | None = None
    hint_ignore: bool = False


@dataclass
class ClassInfo:
    """Metadata for one class definition: bases, decorators, methods, attributes, nested classes and ``@hint.ignore``."""
    name: str
    lineno: int
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    attributes: list[VariableInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    hint_ignore: bool = False


@dataclass
class ImportInfo:
    """One imported name: ``from <module> import <name> as <asname>`` or ``import <name>``.

    *module* keeps its leading dots and is ``None`` for a plain ``import``.
    """
    module: str | None
    name: str
    asname: str | None = None
    lineno: int = 0

    @property
    def local(self) -> str:
        """The name the import binds in the module."""
        if self.asname:
            return self.asname
        return self.name if self.module is not None else self.name.split(".")[0]


@dataclass
class VariableInfo:
    """Metadata for one module-level assignment, annotated or not."""
    name: str
    lineno: int
    annotation_str: str | None = None
    value_repr: str | None = None
    inferred_type_str: str | None = None


@dataclass
class TypeVarInfo:
    """A ``TypeVar``, ``ParamSpec``, ``TypeVarTuple``, ``TypeAlias`` or ``NewType`` declaration.

    *kind* names the construct; *source_str* is the unparsed right-hand side.
    """
    name: str
    lineno: int
    kind: str
    source_str: str


@dataclass
class ASTSymbols:
    """Everything :func:`~stubpy.extend.ast_harvest` collects from one source file.

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
        Contents of ``__all__``, or ``None`` when absent or not a literal list.
    imports : list of ImportInfo
        Top-level imports, in source order.
    skip_file : bool
        ``True`` when the file starts with a ``# stubpy: ignore`` directive.
    """
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    variables: list[VariableInfo] = field(default_factory=list)
    typevar_decls: list[TypeVarInfo] = field(default_factory=list)
    all_exports: list[str] | None = None
    imports: list[ImportInfo] = field(default_factory=list)
    skip_file: bool = False
