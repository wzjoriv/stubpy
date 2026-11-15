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
        Plain decorator names, e.g. ``["classmethod"]``.
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


@dataclass
class ClassInfo:
    """Metadata for one class definition: bases, decorators and direct methods."""
    name: str
    lineno: int
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)


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
    """Everything :func:`~stubpy.ast_harvest` collects from one source file.

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
        Contents of ``__all__``, or ``None`` when absent.
    skip_file : bool
        ``True`` when the file starts with a ``# stubpy: ignore`` directive.
    """
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    variables: list[VariableInfo] = field(default_factory=list)
    typevar_decls: list[TypeVarInfo] = field(default_factory=list)
    all_exports: list[str] | None = None
    skip_file: bool = False
