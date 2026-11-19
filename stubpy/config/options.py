"""
Run options: :class:`Config` and its :class:`UnionStyle`, :class:`AliasStyle` and :class:`VersionBranches` enums.
"""
from __future__ import annotations

import dataclasses
import difflib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from stubpy._constants import DEFAULT_EXCLUDE, DEFAULT_TARGET_PYTHON

from ._docstrings import DocstringTargets
from ._imports import ImportPolicy, coerce_imports, coerce_patterns


class _Choice(str, Enum):
    """A string-valued enum that also accepts its value, case-insensitively."""

    def __str__(self) -> str:
        return self.value

    @classmethod
    def coerce(cls, value: Any, option: str) -> Any:
        """Return the member for *value* (a member or its string value); raise ``ValueError`` otherwise."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            for member in cls:
                if member.value == value.strip().lower():
                    return member
        allowed = ", ".join(repr(m.value) for m in cls)
        raise ValueError(f"Invalid {option}: {value!r}; expected one of {allowed}")


class UnionStyle(_Choice):
    """How unions are written.

    Attributes
    ----------
    MODERN
        PEP 604: ``int | None``.  The default.
    LEGACY
        ``Optional[int]`` and ``Union[int, str]``.

    Examples
    --------
    >>> UnionStyle("legacy") is UnionStyle.LEGACY
    True
    >>> str(UnionStyle.MODERN)
    'modern'
    """
    MODERN = "modern"
    LEGACY = "legacy"


class AliasStyle(_Choice):
    """How type aliases are written.

    Attributes
    ----------
    COMPATIBLE
        ``Name: TypeAlias = rhs``.  The default.
    PEP695
        ``type Name = rhs`` (readable by Python 3.12+ tools).
    AUTO
        ``PEP695`` when stubpy runs on Python 3.12+, else ``COMPATIBLE``.

    Examples
    --------
    >>> AliasStyle("pep695") is AliasStyle.PEP695
    True
    >>> str(AliasStyle.COMPATIBLE)
    'compatible'
    """
    COMPATIBLE = "compatible"
    PEP695 = "pep695"
    AUTO = "auto"


class VersionBranches(_Choice):
    """What happens to ``if`` statements testing ``sys.version_info`` or ``sys.platform``.

    Attributes
    ----------
    EMIT
        Copy the ``if`` / ``elif`` / ``else`` into the stub, each branch with
        the stubs of the names it defines, as typeshed does.  The default.
    RESOLVE
        Keep only the branch the running interpreter takes.

    Examples
    --------
    >>> VersionBranches("resolve") is VersionBranches.RESOLVE
    True
    >>> str(VersionBranches.EMIT)
    'emit'
    """
    EMIT = "emit"
    RESOLVE = "resolve"


_BOOL_FIELDS = (
    "include_private", "respect_all", "include_docstrings", "infer_types", "incremental",
    "resolve_kwargs", "resolve_args", "verbose", "strict",
)
_LIST_FIELDS = ("exclude", "extend_exclude", "targets", "modules")
_CHOICE_FIELDS: dict[str, type[_Choice]] = {
    "union_style": UnionStyle, "alias_style": AliasStyle, "version_branches": VersionBranches,
}


@dataclass(frozen=True)
class Config:
    """Options for one stubpy run.

    Every field has a default, so ``Config()`` is a valid configuration.
    Instances are immutable; use :meth:`replace` to derive a changed copy.
    Enum fields also accept their string values (``union_style="legacy"``).
    Pass one to :func:`~stubpy.render`, :func:`~stubpy.generate` or
    :func:`~stubpy.check`, or read it from a file with :func:`load_config`.
    Pass one to :func:`~stubpy.render`, :func:`~stubpy.generate` or
    :func:`~stubpy.check`, or read it from a file with :func:`load_config`.

    Parameters
    ----------
    imports : str or sequence of str
        Which modules stubpy may import (execute): ``"all"`` (the default),
        ``"none"`` (source analysis only, nothing is executed), ``"stdlib"``,
        or a list of dotted names (``pkg`` or ``pkg.*``, each with its
        submodules) allowed on top of the standard library.  A target whose
        import is blocked, directly or through one of its imports, is stubbed
        from its source with an INFO.  This limits import-time side effects;
        it is not a security sandbox.
    deny_imports : sequence of str
        Dotted names (``pkg`` or ``pkg.*``) never imported, whatever
        *imports* allows.  Defaults to none.
    include_private : bool
        Stub names that start with ``_``.  Defaults to ``False``.
    respect_all : bool
        When a module defines ``__all__``, stub only the public names it
        lists.  Defaults to ``True``.
    include_docstrings : bool
        Use each symbol's docstring as its stub body instead of ``...``.
        Defaults to ``False``.
    infer_types : bool
        Fill in missing parameter and return types from NumPy, Google or
        Sphinx docstrings.  Defaults to ``False``.
    incremental : bool
        Wrap the generated stub in ``# stubpy: auto-generated begin/end``
        markers and merge it into an existing ``.pyi``, keeping manual
        edits outside the markers.  Defaults to ``False``.
    resolve_kwargs : bool
        Expand ``**kwargs`` into the parameters it is forwarded to.
        Defaults to ``True``.
    resolve_args : bool
        Expand ``*args`` into the positional parameters it is forwarded to.
        Defaults to ``True``.
    union_style : UnionStyle or str
        ``"modern"`` (``X | None``) or ``"legacy"`` (``Optional[X]``).
        Defaults to ``"modern"``.
    alias_style : AliasStyle or str
        ``"compatible"`` (``X: TypeAlias = ...``), ``"pep695"``
        (``type X = ...``) or ``"auto"``.  Defaults to ``"compatible"``.
    version_branches : VersionBranches or str
        ``"emit"`` copies ``if sys.version_info ...`` / ``if sys.platform ...``
        blocks into the stub with every branch; ``"resolve"`` keeps only the
        branch the running interpreter takes.  Defaults to ``"emit"``.
    exclude : sequence of str
        Patterns of files and folders a folder run skips; setting it
        replaces the defaults (hidden names ``.*``, ``__pycache__``,
        ``build``, ``dist``, ``.venv``, ``venv``, ``*.egg-info``, ``.git``,
        ``.tox``, ``.nox`` and ``<non-identifier>``, any folder or module
        name Python cannot import).  A pattern with ``/`` matches the path
        relative to the folder target, one without matches any single name.
        Files named directly are never skipped.
    extend_exclude : sequence of str
        More patterns, added to *exclude*.
    output_dir : str or None
        Stub root used when :func:`~stubpy.generate` gets no ``output``;
        ``None`` writes each stub next to its source.
    targets : sequence of str
        Paths, folders or globs to act on when no target is given.
    modules : sequence of str
        Dotted module names to act on when no target is given.
    verbose : bool
        Report INFO diagnostics on the command line.  Defaults to ``False``.
    strict : bool
        Count WARNING diagnostics as failures.  Defaults to ``False``.
    docstrings : DocstringTargets or mapping
        The ``[tool.stubpy.docstrings]`` table: the hand-written stubs
        ``stubpy docstrings`` syncs when given no STUB.
    target_python : str
        Oldest Python (``"3.10"``) the stubs must import on: ``typing`` names
        added later (``Self``, ``override``, ``TypeIs``, ``deprecated``, ...)
        are imported from ``typing_extensions``.  Defaults to ``"3.10"``.

    Raises
    ------
    ValueError
        If an enum field gets an unknown value.
    TypeError
        If a flag is not a ``bool`` or a list field is not a list of strings.

    See Also
    --------
    load_config : Read a configuration from ``stubpy.toml`` or ``pyproject.toml``.
    Config.from_dict : Build a configuration from a mapping.

    Examples
    --------
    >>> cfg = Config(imports="none", include_private=True)
    >>> cfg.may_import
    False
    >>> cfg.replace(union_style="legacy").union_style.value
    'legacy'
    """
    imports: str | tuple[str, ...] = "all"
    deny_imports: tuple[str, ...] = ()
    include_private: bool = False
    respect_all: bool = True
    include_docstrings: bool = False
    infer_types: bool = False
    incremental: bool = False
    resolve_kwargs: bool = True
    resolve_args: bool = True
    union_style: UnionStyle = UnionStyle.MODERN
    alias_style: AliasStyle = AliasStyle.COMPATIBLE
    version_branches: VersionBranches = VersionBranches.EMIT
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE
    extend_exclude: tuple[str, ...] = field(default_factory=tuple)
    output_dir: str | None = None
    targets: tuple[str, ...] = field(default_factory=tuple)
    modules: tuple[str, ...] = field(default_factory=tuple)
    verbose: bool = False
    strict: bool = False
    target_python: str = DEFAULT_TARGET_PYTHON
    docstrings: DocstringTargets = DocstringTargets()

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_python", _version_text(self.target_python))
        for name, enum in _CHOICE_FIELDS.items():
            object.__setattr__(self, name, enum.coerce(getattr(self, name), name))
        for name in _BOOL_FIELDS:
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool, not {type(getattr(self, name)).__name__}")
        for name in _LIST_FIELDS:
            object.__setattr__(self, name, _string_tuple(getattr(self, name), name))
        if self.output_dir is not None:
            object.__setattr__(self, "output_dir", str(self.output_dir))
        object.__setattr__(self, "docstrings", DocstringTargets.coerce(self.docstrings))
        object.__setattr__(self, "imports", coerce_imports(self.imports))
        object.__setattr__(self, "deny_imports", coerce_patterns(self.deny_imports, "deny_imports"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Config:
        """Build a config from a mapping such as a ``[tool.stubpy]`` table.

        Keys are field names; dashes are read as underscores.

        Parameters
        ----------
        data : mapping
            Option names to values.

        Returns
        -------
        Config
            The options over the defaults.

        Raises
        ------
        ValueError
            On an unknown key (with the closest valid name) or an invalid value.

        See Also
        --------
        load_config : Read the mapping from a configuration file.

        Examples
        --------
        >>> Config.from_dict({"include-private": True, "imports": "stdlib"}).imports
        'stdlib'
        """
        names = [f.name for f in dataclasses.fields(cls)]
        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            name = str(key).replace("-", "_")
            if name not in names:
                close = difflib.get_close_matches(name, names, n=1)
                hint = f"; did you mean {close[0]!r}?" if close else ""
                raise ValueError(f"Unknown stubpy option {key!r}{hint}")
            kwargs[name] = value
        return cls(**kwargs)

    @property
    def exclude_patterns(self) -> tuple[str, ...]:
        """``exclude`` followed by ``extend_exclude``, as a tuple of patterns."""
        return (*self.exclude, *self.extend_exclude)

    @property
    def may_import(self) -> bool:
        """False when ``imports`` is ``"none"``: nothing is executed."""
        return self.imports != "none"

    @property
    def import_policy(self) -> ImportPolicy:
        """The :class:`ImportPolicy` of ``imports`` and ``deny_imports``."""
        return ImportPolicy(self.imports, self.deny_imports)

    @property
    def target_version(self) -> tuple[int, int]:
        """*target_python* as ``(major, minor)``."""
        major, minor = self.target_python.split(".")
        return int(major), int(minor)

    def replace(self, **changes: Any) -> Config:
        """Return a copy with *changes* applied and validated.

        Parameters
        ----------
        **changes
            Field names and their new values, as accepted by :class:`Config`.

        Returns
        -------
        Config
            A new configuration; the original is unchanged.

        Raises
        ------
        TypeError
            If a name is not a field, or a value has the wrong type.
        ValueError
            If an enum field gets an unknown value.

        See Also
        --------
        Config.from_dict : Build a configuration from a mapping.

        Examples
        --------
        >>> Config().replace(include_private=True).include_private
        True
        """
        return dataclasses.replace(self, **changes)


def _version_text(value: Any) -> str:
    """Return a ``"3.X"`` version string, raising ``ValueError`` for anything else."""
    text = str(value).strip()
    if not re.fullmatch(r"3\.\d{1,2}", text):
        raise ValueError(f"target_python must look like '3.10', not {value!r}")
    return text


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    """Return *value* as a tuple of strings; a lone string is one item."""
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Iterable):
        raise TypeError(f"{name} must be a list of strings, not {type(value).__name__}")
    items = tuple(value)
    for item in items:
        if not isinstance(item, (str, bytes)) and not hasattr(item, "__fspath__"):
            raise TypeError(f"{name} must contain strings, not {type(item).__name__}")
    return tuple(str(item) for item in items)
