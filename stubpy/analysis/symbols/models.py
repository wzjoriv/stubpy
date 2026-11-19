"""Symbol classes: the typed entries of a :class:`~stubpy.SymbolTable`."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo, TypeVarInfo, VariableInfo


class SymbolKind(Enum):
    """Category of a stub symbol."""
    CLASS = "class"
    FUNCTION = "function"
    VARIABLE = "variable"
    ALIAS = "alias"
    OVERLOAD = "overload"


@dataclass
class StubSymbol:
    """Base class for all symbols.

    Parameters
    ----------
    name : str
        Symbol name.
    kind : SymbolKind
        Symbol category.
    lineno : int
        Source line of the definition; symbols are emitted in this order.
    branch : tuple
        The version branches (``(VersionBlock, index)`` pairs) the
        definition sits in; ``()`` when unconditional.
    dormant : bool
        The running interpreter does not take *branch*, so there is no live object.
    """
    name: str
    kind: SymbolKind
    lineno: int
    branch: tuple = ()
    dormant: bool = False


@dataclass
class ClassSymbol(StubSymbol):
    """A class definition.

    Parameters
    ----------
    live_type : type or None
        The runtime class; ``None`` when the module was not imported.
    ast_info : ClassInfo or None
        Metadata from the AST pre-pass.

    Examples
    --------
    >>> ClassSymbol(name="Widget", lineno=5).kind
    <SymbolKind.CLASS: 'class'>
    """
    live_type: type | None = None
    ast_info: ClassInfo | None = None

    def __init__(
        self,
        name: str,
        lineno: int,
        live_type: type | None = None,
        ast_info: ClassInfo | None = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.CLASS, lineno=lineno)
        self.live_type = live_type
        self.ast_info = ast_info


@dataclass
class FunctionSymbol(StubSymbol):
    """A top-level function definition.

    Parameters
    ----------
    live_func : callable or None
        The runtime function; ``None`` when the module was not imported.
    ast_info : FunctionInfo or None
        Metadata from the AST pre-pass.
    is_async : bool
        Taken from *ast_info* when given.

    Examples
    --------
    >>> FunctionSymbol(name="greet", lineno=3, is_async=True).is_async
    True
    """
    live_func: Any | None = None
    ast_info: FunctionInfo | None = None
    is_async: bool = False

    def __init__(
        self,
        name: str,
        lineno: int,
        live_func: Any | None = None,
        ast_info: FunctionInfo | None = None,
        is_async: bool = False,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.FUNCTION, lineno=lineno)
        self.live_func = live_func
        self.ast_info = ast_info
        self.is_async = ast_info.is_async if ast_info is not None else is_async


@dataclass
class VariableSymbol(StubSymbol):
    """A module-level variable.

    Parameters
    ----------
    live_value : Any
        The runtime value; ``None`` when the module was not imported.
    annotation_str : str or None
        Annotation from the source.
    inferred_type_str : str or None
        Type inferred from the value when there is no annotation.
    ast_info : VariableInfo or None
        Metadata from the AST pre-pass.

    Examples
    --------
    >>> VariableSymbol(name="MAX", lineno=1, annotation_str="int").effective_type_str
    'int'
    """
    live_value: Any = None
    annotation_str: str | None = None
    inferred_type_str: str | None = None
    ast_info: VariableInfo | None = None

    def __init__(
        self,
        name: str,
        lineno: int,
        live_value: Any = None,
        annotation_str: str | None = None,
        inferred_type_str: str | None = None,
        ast_info: VariableInfo | None = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.VARIABLE, lineno=lineno)
        self.live_value = live_value
        self.annotation_str = annotation_str
        self.inferred_type_str = inferred_type_str
        self.ast_info = ast_info

    @property
    def effective_type_str(self) -> str | None:
        """The annotation if present, else the inferred type."""
        return self.annotation_str or self.inferred_type_str


@dataclass
class AliasSymbol(StubSymbol):
    """A ``TypeAlias``, ``TypeVar``, ``ParamSpec``, ``TypeVarTuple`` or ``NewType`` declaration.

    Parameters
    ----------
    ast_info : TypeVarInfo or None
        Metadata from the AST pre-pass.
    live_obj : Any
        The runtime object, if available.
    """
    ast_info: TypeVarInfo | None = None
    live_obj: Any = None

    def __init__(
        self,
        name: str,
        lineno: int,
        ast_info: TypeVarInfo | None = None,
        live_obj: Any = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.ALIAS, lineno=lineno)
        self.ast_info = ast_info
        self.live_obj = live_obj


@dataclass
class OverloadGroup(StubSymbol):
    """The ``@overload`` variants sharing one function name.

    Parameters
    ----------
    variants : list of FunctionSymbol
        One entry per ``@overload`` definition, in source order.
    live_func : callable or None
        The runtime implementation.
    """
    variants: list[FunctionSymbol] = field(default_factory=list)
    live_func: Any | None = None

    def __init__(
        self,
        name: str,
        lineno: int,
        variants: list[FunctionSymbol] | None = None,
        live_func: Any | None = None,
    ) -> None:
        super().__init__(name=name, kind=SymbolKind.OVERLOAD, lineno=lineno)
        self.variants = variants if variants is not None else []
        self.live_func = live_func
