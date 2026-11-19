"""
Static name resolution: what a name or dotted name refers to in a harvested module.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

from stubpy._constants import PARTIAL_NAMES
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo, LocalImport

from .index import SourceIndex, SourceModule


@dataclass(eq=False)
class ModuleRef:
    """A harvested module."""
    module: SourceModule


@dataclass(eq=False)
class ClassRef:
    """A class defined in a harvested module; *outer* holds the enclosing classes of a nested one."""
    module: SourceModule
    info: ClassInfo

    @property
    def key(self) -> str:
        """A run-unique name for cycle guards."""
        return f"{self.module.name}.{self.info.name}"


@dataclass(eq=False)
class FuncRef:
    """A function (or method, with *owner*) defined in a harvested module; *overloads* are its variants."""
    module: SourceModule
    info: FunctionInfo
    owner: ClassRef | None = None
    overloads: list[FunctionInfo] = field(default_factory=list)

    @property
    def key(self) -> str:
        """A run-unique name for cycle guards."""
        owner = f"{self.owner.info.name}." if self.owner is not None else ""
        return f"{self.module.name}.{owner}{self.info.name}"


@dataclass(eq=False)
class PartialRef:
    """``functools.partial(target, *args, **keywords)`` stored in a variable."""
    target: Ref
    positional: int
    keywords: dict[str, str]


Ref = ModuleRef | ClassRef | FuncRef | PartialRef

_MAX_DEPTH = 24


def _functions(infos: list[FunctionInfo], name: str) -> tuple[FunctionInfo | None, list[FunctionInfo]]:
    """Return the implementation of *name* among *infos* (the last definition) and its ``@overload`` variants."""
    found = [f for f in infos if f.name == name]
    impl = [f for f in found if not f.is_overload]
    overloads = [f for f in found if f.is_overload]
    if impl:
        return impl[-1], overloads
    return (overloads[-1], overloads) if overloads else (None, [])


def method_ref(cref: ClassRef, name: str) -> FuncRef | None:
    """Return the method *name* defined directly on *cref*."""
    impl, overloads = _functions(cref.info.methods, name)
    return FuncRef(cref.module, impl, cref, overloads) if impl is not None else None


class Resolver:
    """Resolve names through a :class:`SourceIndex`, following imports, aliases and partials."""

    def __init__(self, index: SourceIndex) -> None:
        self.index = index

    def lookup(self, module: SourceModule, name: str, _depth: int = 0) -> Ref | None:
        """Return what *name* is bound to at the top level of *module*."""
        if _depth > _MAX_DEPTH:
            return None
        symbols = module.symbols
        cls = next((c for c in reversed(symbols.classes) if c.name == name), None)
        if cls is not None:
            return ClassRef(module, cls)
        impl, overloads = _functions(symbols.functions, name)
        if impl is not None:
            return FuncRef(module, impl, None, overloads)
        for imp in reversed(symbols.imports):
            if imp.local == name and imp.name != "*":
                return self._imported(module, imp.module, imp.name, imp.asname, _depth)
        var = next((v for v in reversed(symbols.variables) if v.name == name), None)
        if var is not None and var.value_repr:
            return self.expression(module, var.value_repr, None, _depth + 1)
        for imp in symbols.imports:
            if imp.name == "*" and imp.module:
                star = self.index.import_from(module, imp.module)
                found = self.lookup(star, name, _depth + 1) if star is not None else None
                if found is not None:
                    return found
        return None

    def _imported(self, module: SourceModule, source: str | None, name: str, asname: str | None,
                  depth: int) -> Ref | None:
        """Resolve one import statement's binding."""
        if source is None:
            dotted = name if asname else name.split(".")[0]
            target = self.index.import_from(module, dotted)
            return ModuleRef(target) if target is not None else None
        owner = self.index.import_from(module, source)
        if owner is None:
            return None
        found = self.lookup(owner, name, depth + 1)
        if found is not None:
            return found
        sub = self.index.import_from(module, f"{source}.{name}" if source.strip(".") else f"{source}{name}")
        return ModuleRef(sub) if sub is not None else None

    def local(self, module: SourceModule, spec: LocalImport) -> Ref | None:
        """Resolve a name bound by an import inside a function body."""
        dots = "." * spec.level
        if spec.attr is None:
            target = self.index.import_from(module, spec.module)
            return ModuleRef(target) if target is not None else None
        return self._imported(module, f"{dots}{spec.module}", spec.attr, None, 0)

    def attribute(self, ref: Ref | None, part: str) -> Ref | None:
        """Return ``ref.part``: a module member or submodule, a method or a nested class."""
        if isinstance(ref, ModuleRef):
            found = self.lookup(ref.module, part)
            if found is not None:
                return found
            sub = self.index.import_from(ref.module, f"{ref.module.name}.{part}")
            return ModuleRef(sub) if sub is not None else None
        if isinstance(ref, ClassRef):
            nested = next((c for c in ref.info.classes if c.name == part), None)
            if nested is not None:
                return ClassRef(ref.module, nested)
            return self.inherited_method(ref, part)
        return None

    def inherited_method(self, cref: ClassRef, name: str) -> FuncRef | None:
        """Return method *name* as looked up on *cref* (defined on it or a known ancestor), owned by *cref*."""
        from ._mro import static_mro

        for klass in static_mro(self, cref):
            found = method_ref(klass, name) if isinstance(klass, ClassRef) else None
            if found is not None:
                return FuncRef(found.module, found.info, cref, found.overloads)
        return None

    def dotted(self, module: SourceModule, name: str, caller: FunctionInfo | None = None,
               _depth: int = 0) -> Ref | None:
        """Resolve ``a.b.c`` from *module*; the head may be bound by an import inside *caller*."""
        head, *rest = name.split(".")
        spec = caller.local_imports.get(head) if caller is not None else None
        ref = self.local(module, spec) if spec is not None else self.lookup(module, head, _depth)
        for part in rest:
            ref = self.attribute(ref, part)
        return ref

    def expression(self, module: SourceModule, text: str, caller: FunctionInfo | None, _depth: int = 0,
                   ) -> Ref | None:
        """Resolve the source text of a value: a dotted name or a ``functools.partial(...)`` call."""
        try:
            node = ast.parse(text, mode="eval").body
        except SyntaxError:
            return None
        name = _dotted_text(node)
        if name is not None:
            return self.dotted(module, name, caller, _depth)
        if (
            isinstance(node, ast.Call) and _dotted_text(node.func) in PARTIAL_NAMES and node.args
            and not any(isinstance(a, ast.Starred) for a in node.args)
            and all(k.arg is not None for k in node.keywords)
        ):
            target_name = _dotted_text(node.args[0])
            target = self.dotted(module, target_name, caller, _depth + 1) if target_name else None
            if target is None:
                return None
            keywords = {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg is not None}
            return PartialRef(target, len(node.args) - 1, keywords)
        return None


def _dotted_text(node: ast.AST) -> str | None:
    """Return ``a.b.c`` for a chain of attributes rooted at a name, else ``None``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])
