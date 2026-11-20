"""
Harvested module-level facts: import statements, variables and type variables.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ._part_models import Branch
from ._part_models import ConsumedHints as ConsumedHints
from ._part_models import NonLiteralDefault as NonLiteralDefault
from ._part_models import VersionBlock as VersionBlock
from ._part_models import on_taken_path as on_taken_path


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
