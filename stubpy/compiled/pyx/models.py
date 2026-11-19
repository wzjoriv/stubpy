"""What a Cython source declares that Python can see: functions, ``cdef class`` members and enums."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PyxParam:
    """One argument: *ctype* is the C or Python type as written (``None`` when untyped), *default* its source."""
    name: str
    ctype: str | None = None
    default: str | None = None
    star: str = ""


@dataclass
class PyxFunction:
    """A ``def`` or ``cpdef`` function or method; *kw_only* is the index of a bare ``*``."""
    name: str
    params: list[PyxParam] = field(default_factory=list)
    returns: str | None = None
    doc: str | None = None
    decorators: list[str] = field(default_factory=list)
    kw_only: int | None = None

    def embedsignature(self) -> str:
        """The signature as Cython ``embedsignature`` writes it: ``name(int n, x=1) -> double``."""
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
    """A ``cdef class`` (or plain ``class``); *attributes* are ``cdef public`` / ``readonly`` fields."""
    name: str
    bases: list[str] = field(default_factory=list)
    doc: str | None = None
    methods: list[PyxFunction] = field(default_factory=list)
    attributes: dict[str, tuple[str, bool]] = field(default_factory=dict)


@dataclass
class PyxEnum:
    """A ``cpdef enum`` (visible to Python) with its members' values when they are literal integers."""
    name: str
    members: list[tuple[str, int | None]] = field(default_factory=list)


@dataclass
class PyxModule:
    """Everything one ``.pyx`` file exposes, in source order."""
    functions: list[PyxFunction] = field(default_factory=list)
    classes: list[PyxClass] = field(default_factory=list)
    enums: list[PyxEnum] = field(default_factory=list)
    doc: str | None = None

    def qualify_enum_defaults(self) -> PyxModule:
        """Rewrite bare enum-member defaults (``DC``) as ``TableClass.DC``; return *self*."""
        owner = {member: e.name for e in self.enums for member, _ in e.members}
        for fn in self.signatures().values():
            for p in fn.params:
                if p.default in owner:
                    p.default = f"{owner[p.default]}.{p.default}"
        return self

    def signatures(self) -> dict[str, PyxFunction]:
        """``{qualified name: function}`` for module functions and class methods."""
        found = {f.name: f for f in self.functions}
        for cls in self.classes:
            found.update({f"{cls.name}.{m.name}": m for m in cls.methods})
        return found
