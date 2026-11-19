"""
What a Cython source declares that Python can see: functions, ``cdef class`` members and enums.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PyxParam:
    """One argument of a Cython function.

    Attributes
    ----------
    name : str
        The argument name.
    ctype : str or None
        The C or Python type as written; ``None`` when untyped.
    default : str or None
        The default's source text; ``None`` when there is none.
    star : str
        ``"*"`` or ``"**"`` for a variadic argument, else empty.
    """
    name: str
    ctype: str | None = None
    default: str | None = None
    star: str = ""


@dataclass
class PyxFunction:
    """A ``def`` or ``cpdef`` function or method.

    Attributes
    ----------
    name : str
        The function name.
    params : list of PyxParam
        The arguments in order.
    returns : str or None
        The return type as written, if any.
    doc : str or None
        The docstring, if any.
    decorators : list of str
        Decorator source texts.
    kw_only : int or None
        Index of the argument a bare ``*`` precedes; ``None`` when absent.
    """
    name: str
    params: list[PyxParam] = field(default_factory=list)
    returns: str | None = None
    doc: str | None = None
    decorators: list[str] = field(default_factory=list)
    kw_only: int | None = None

    def embedsignature(self) -> str:
        """Render the signature as Cython ``embedsignature`` writes it.

        Returns
        -------
        str
            Text such as ``name(int n, x=1) -> double``.

        Examples
        --------
        >>> fn = PyxFunction("scale", [PyxParam("n", "int"), PyxParam("x", None, "1")], "double")
        >>> fn.embedsignature()
        'scale(int n, x=1) -> double'
        """
        parts: list[str] = []
        for i, p in enumerate(self.params):
            if self.kw_only == i:
                parts.append("*")
            typed = f"{p.ctype} {p.name}" if p.ctype else p.name
            parts.append(f"{p.star}{typed}" + (f"={p.default}" if p.default is not None else ""))
        if self.kw_only is not None and self.kw_only >= len(self.params):
            parts.append("*")
        ret = f" -> {self.returns}" if self.returns else ""
        return f"{self.name}({', '.join(parts)}){ret}"


@dataclass
class PyxClass:
    """A ``cdef class`` or plain ``class``.

    Attributes
    ----------
    name : str
        The class name.
    bases : list of str
        Base class texts.
    doc : str or None
        The docstring, if any.
    methods : list of PyxFunction
        The methods in source order.
    attributes : dict of str to tuple of (str, bool)
        ``cdef public`` / ``readonly`` fields: name to ``(type, writable)``.
    """
    name: str
    bases: list[str] = field(default_factory=list)
    doc: str | None = None
    methods: list[PyxFunction] = field(default_factory=list)
    attributes: dict[str, tuple[str, bool]] = field(default_factory=dict)


@dataclass
class PyxEnum:
    """A ``cpdef enum`` visible to Python.

    Attributes
    ----------
    name : str
        The enum name.
    members : list of tuple of (str, int or None)
        Member names with their values; ``None`` unless a literal integer.
    """
    name: str
    members: list[tuple[str, int | None]] = field(default_factory=list)


@dataclass
class PyxModule:
    """Everything one ``.pyx`` file exposes, in source order.

    Attributes
    ----------
    functions : list of PyxFunction
        Module-level functions.
    classes : list of PyxClass
        Classes.
    enums : list of PyxEnum
        ``cpdef`` enums.
    doc : str or None
        The module docstring, if any.
    """
    functions: list[PyxFunction] = field(default_factory=list)
    classes: list[PyxClass] = field(default_factory=list)
    enums: list[PyxEnum] = field(default_factory=list)
    doc: str | None = None

    def qualify_enum_defaults(self) -> PyxModule:
        """Rewrite bare enum-member defaults as qualified names.

        A default ``DC`` of an enum ``TableClass`` becomes ``TableClass.DC``.

        Returns
        -------
        PyxModule
            This module, changed in place.

        Examples
        --------
        >>> fn = PyxFunction("f", [PyxParam("t", None, "DC")])
        >>> mod = PyxModule([fn], enums=[PyxEnum("TableClass", [("DC", 0)])])
        >>> mod.qualify_enum_defaults().functions[0].params[0].default
        'TableClass.DC'
        """
        owner = {member: e.name for e in self.enums for member, _ in e.members}
        for fn in self.signatures().values():
            for p in fn.params:
                if p.default in owner:
                    p.default = f"{owner[p.default]}.{p.default}"
        return self

    def signatures(self) -> dict[str, PyxFunction]:
        """Map qualified names to the functions and methods of the module.

        Returns
        -------
        dict of str to PyxFunction
            Module functions by name and class methods as ``Class.method``.

        Examples
        --------
        >>> m = PyxModule([PyxFunction("f")], [PyxClass("C", methods=[PyxFunction("m")])])
        >>> sorted(m.signatures())
        ['C.m', 'f']
        """
        found = {f.name: f for f in self.functions}
        for cls in self.classes:
            found.update({f"{cls.name}.{m.name}": m for m in cls.methods})
        return found
